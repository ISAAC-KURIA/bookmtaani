"""
Tests for the Paystack payment flow. All Paystack network calls are mocked,
so these run offline and never touch real money.
"""
import hashlib
import hmac
import json
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from core.models import UserProfile, Business, Service, Booking, Payment


# ---------------------------------------------------------------------------
# Same Python 3.14 + Django 5.1 template-context workaround used in test_booking.py
# ---------------------------------------------------------------------------
def _patched_context_copy(self):
    cls = type(self)
    duplicate = cls.__new__(cls)
    duplicate.__dict__.update(self.__dict__)
    duplicate.dicts = self.dicts[:]
    return duplicate

from django.template.context import RequestContext, Context  # noqa: E402
RequestContext.__copy__ = _patched_context_copy
Context.__copy__ = _patched_context_copy


TEST_SECRET = 'sk_test_unit_test_key'


def _response(payload, status_code=200):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = payload
    return r


@override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET, PAYSTACK_CURRENCY='KES')
class PaystackFlowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner1', password='x')
        UserProfile.objects.create(user=self.owner, role='owner')
        self.customer = User.objects.create_user('cust1', password='x', email='cust1@example.com')
        UserProfile.objects.create(user=self.customer, role='customer')
        self.other = User.objects.create_user('cust2', password='x', email='cust2@example.com')
        UserProfile.objects.create(user=self.other, role='customer')

        biz = Business.objects.create(owner=self.owner, name='Test Biz', category='kinyozi', town='Kisii')
        self.service = Service.objects.create(business=biz, name='Haircut', price=Decimal('500.00'), duration_minutes=30)
        self.booking = Booking.objects.create(
            customer=self.customer, service=self.service,
            date=date.today() + timedelta(days=2),
            start_time=time(10, 0), end_time=time(10, 30),
        )
        self.client = Client()
        self.client.login(username='cust1', password='x')
        self.init_url = reverse('core:paystack_initialize', args=[self.booking.id])
        self.verify_url = reverse('core:paystack_verify', args=[self.booking.id])
        self.webhook_url = reverse('core:paystack_webhook')

    # ---- helpers ---------------------------------------------------------
    def _initialize(self, email=None):
        body = {'email': email} if email is not None else {}
        with patch('core.views.requests.post') as post:
            post.return_value = _response({'status': True, 'data': {'access_code': 'AC123', 'reference': 'x'}})
            res = self.client.post(self.init_url, data=json.dumps(body), content_type='application/json')
        return res, post

    def _success_payload(self, payment, **overrides):
        data = {
            'status': 'success',
            'reference': payment.transaction_ref,
            'amount': int(payment.amount * 100),
            'currency': 'KES',
            'channel': 'mobile_money',
        }
        data.update(overrides)
        return data

    def _signed_webhook(self, event, secret=TEST_SECRET, bad_signature=False):
        raw = json.dumps(event).encode()
        sig = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
        if bad_signature:
            sig = 'deadbeef'
        return self.client.post(self.webhook_url, data=raw, content_type='application/json',
                                HTTP_X_PAYSTACK_SIGNATURE=sig)

    # ---- pages -----------------------------------------------------------
    def test_pay_page_renders_with_paystack_script(self):
        res = self.client.get(reverse('core:pay_booking', args=[self.booking.id]) + '?autopay=1')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'https://js.paystack.co/v2/inline.js')
        self.assertContains(res, 'id="pay-btn"')
        self.assertContains(res, 'KES 500')
        self.assertTrue(res.context['pay_config']['autopay'])

    def test_autopay_off_without_email(self):
        self.customer.email = ''
        self.customer.save()
        res = self.client.get(reverse('core:pay_booking', args=[self.booking.id]) + '?autopay=1')
        self.assertFalse(res.context['pay_config']['autopay'])

    def test_other_customer_cannot_open_pay_page(self):
        c = Client()
        c.login(username='cust2', password='x')
        res = c.get(reverse('core:pay_booking', args=[self.booking.id]))
        self.assertEqual(res.status_code, 404)

    def test_booking_detail_shows_pay_button_when_unpaid(self):
        res = self.client.get(reverse('core:booking_detail', args=[self.booking.id]))
        self.assertContains(res, 'Pay Now')

    def test_confirm_redirects_to_pay_page_with_autopay(self):
        # booking_confirm -> create_booking is exercised in test_booking; here we only check the redirect target.
        with patch('core.views.get_available_slots', return_value=['10:00']), \
             patch('core.views.create_booking', return_value=self.booking), \
             patch('core.views.create_sms_notifications'):
            res = self.client.post(reverse('core:booking_confirm', args=[
                self.service.id, self.booking.date.isoformat(), '10:00']))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(
            res.url, reverse('core:pay_booking', args=[self.booking.id]) + '?autopay=1')

    # ---- initialize ------------------------------------------------------
    def test_initialize_returns_access_code_and_uses_server_side_amount(self):
        res, post = self._initialize(email='me@example.com')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['access_code'], 'AC123')

        sent = post.call_args.kwargs['json']
        self.assertEqual(sent['amount'], 50000)            # KES 500.00 -> 50000
        self.assertEqual(sent['currency'], 'KES')
        self.assertEqual(sent['email'], 'me@example.com')
        self.assertEqual(sent['reference'], res.json()['reference'])
        self.assertIn(f'Bearer {TEST_SECRET}', post.call_args.kwargs['headers']['Authorization'])

        pay = Payment.objects.get(booking=self.booking)
        self.assertEqual(pay.status, Payment.STATUS_PENDING)
        self.assertEqual(pay.method, 'paystack')
        self.assertEqual(pay.transaction_ref, sent['reference'])
        self.assertEqual(pay.amount, Decimal('500.00'))

    def test_initialize_ignores_amount_sent_by_browser(self):
        body = {'email': 'me@example.com', 'amount': 1}
        with patch('core.views.requests.post') as post:
            post.return_value = _response({'status': True, 'data': {'access_code': 'AC1'}})
            self.client.post(self.init_url, data=json.dumps(body), content_type='application/json')
        self.assertEqual(post.call_args.kwargs['json']['amount'], 50000)

    def test_initialize_requires_valid_email_when_user_has_none(self):
        self.customer.email = ''
        self.customer.save()
        res, post = self._initialize(email='not-an-email')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['field'], 'email')
        post.assert_not_called()

    def test_initialize_falls_back_to_account_email(self):
        res, post = self._initialize()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(post.call_args.kwargs['json']['email'], 'cust1@example.com')

    def test_initialize_rejects_other_customers_booking(self):
        c = Client()
        c.login(username='cust2', password='x')
        res = c.post(self.init_url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 404)

    def test_initialize_requires_post_and_login(self):
        self.assertEqual(self.client.get(self.init_url).status_code, 405)
        anon = Client()
        res = anon.post(self.init_url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 302)

    @override_settings(PAYSTACK_SECRET_KEY='sk_test_REPLACE_WITH_YOUR_SECRET_KEY')
    def test_initialize_reports_unconfigured_keys(self):
        with patch('core.views.requests.post') as post:
            res = self.client.post(self.init_url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 503)
        self.assertIn('not configured', res.json()['error'])
        post.assert_not_called()

    def test_initialize_surfaces_paystack_error(self):
        with patch('core.views.requests.post') as post:
            post.return_value = _response({'status': False, 'message': 'Currency not supported by merchant'}, 400)
            res = self.client.post(self.init_url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 502)
        self.assertIn('Currency', res.json()['error'])
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_initialize_cancelled_booking_rejected(self):
        self.booking.status = Booking.STATUS_CANCELLED
        self.booking.save()
        res, post = self._initialize()
        self.assertEqual(res.status_code, 409)
        post.assert_not_called()

    def test_retry_creates_new_reference_when_old_attempt_unpaid(self):
        self._initialize()
        first_ref = Payment.objects.get(booking=self.booking).transaction_ref
        with patch('core.views.requests.get') as get, patch('core.views.requests.post') as post:
            get.return_value = _response({'status': True, 'data': {'status': 'abandoned'}})
            post.return_value = _response({'status': True, 'data': {'access_code': 'AC2'}})
            res = self.client.post(self.init_url, data='{}', content_type='application/json')
        self.assertEqual(res.json()['access_code'], 'AC2')
        pay = Payment.objects.get(booking=self.booking)
        self.assertNotEqual(pay.transaction_ref, first_ref)
        self.assertEqual(pay.status, Payment.STATUS_PENDING)

    def test_retry_detects_earlier_attempt_that_actually_succeeded(self):
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        with patch('core.views.requests.get') as get, patch('core.views.requests.post') as post:
            get.return_value = _response({'status': True, 'data': self._success_payload(pay)})
            res = self.client.post(self.init_url, data='{}', content_type='application/json')
        self.assertTrue(res.json()['already_paid'])
        post.assert_not_called()
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.STATUS_PAID)

    # ---- verify ----------------------------------------------------------
    def test_verify_success_marks_paid_and_confirms_booking(self):
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        with patch('core.views.requests.get') as get:
            get.return_value = _response({'status': True, 'data': self._success_payload(pay)})
            res = self.client.post(self.verify_url)
        self.assertEqual(res.json()['status'], 'paid')
        pay.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(pay.status, Payment.STATUS_PAID)
        self.assertEqual(pay.channel, 'mobile_money')
        self.assertIsNotNone(pay.paid_at)
        self.assertEqual(self.booking.status, Booking.STATUS_CONFIRMED)

    def test_verify_wrong_amount_is_not_marked_paid(self):
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        with patch('core.views.requests.get') as get:
            get.return_value = _response({'status': True, 'data': self._success_payload(pay, amount=100)})
            res = self.client.post(self.verify_url)
        self.assertEqual(res.json()['status'], 'mismatch')
        pay.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(pay.status, Payment.STATUS_PENDING)
        self.assertEqual(self.booking.status, Booking.STATUS_PENDING)

    def test_verify_wrong_currency_is_not_marked_paid(self):
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        with patch('core.views.requests.get') as get:
            get.return_value = _response({'status': True, 'data': self._success_payload(pay, currency='NGN')})
            res = self.client.post(self.verify_url)
        self.assertEqual(res.json()['status'], 'mismatch')

    def test_verify_failed_transaction_marks_failed(self):
        self._initialize()
        with patch('core.views.requests.get') as get:
            get.return_value = _response({'status': True, 'data': {'status': 'failed'}})
            res = self.client.post(self.verify_url)
        self.assertEqual(res.json()['status'], 'failed')
        self.assertEqual(Payment.objects.get(booking=self.booking).status, Payment.STATUS_DECLINED)

    def test_verify_paystack_unreachable(self):
        self._initialize()
        import requests as real_requests
        with patch('core.views.requests.get', side_effect=real_requests.ConnectionError):
            res = self.client.post(self.verify_url)
        self.assertEqual(res.status_code, 502)
        self.assertEqual(Payment.objects.get(booking=self.booking).status, Payment.STATUS_PENDING)

    def test_verify_without_payment_started(self):
        res = self.client.post(self.verify_url)
        self.assertEqual(res.status_code, 404)

    def test_verify_other_customer_blocked(self):
        self._initialize()
        c = Client()
        c.login(username='cust2', password='x')
        res = c.post(self.verify_url)
        self.assertEqual(res.status_code, 404)

    # ---- webhook ---------------------------------------------------------
    def test_webhook_rejects_bad_signature(self):
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        res = self._signed_webhook(
            {'event': 'charge.success', 'data': self._success_payload(pay)}, bad_signature=True)
        self.assertEqual(res.status_code, 401)
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.STATUS_PENDING)

    def test_webhook_rejects_signature_from_wrong_key(self):
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        res = self._signed_webhook(
            {'event': 'charge.success', 'data': self._success_payload(pay)}, secret='sk_test_attacker')
        self.assertEqual(res.status_code, 401)

    def test_webhook_charge_success_marks_paid(self):
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        res = self._signed_webhook({'event': 'charge.success', 'data': self._success_payload(pay)})
        self.assertEqual(res.status_code, 200)
        pay.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(pay.status, Payment.STATUS_PAID)
        self.assertEqual(self.booking.status, Booking.STATUS_CONFIRMED)

    def test_webhook_is_idempotent_and_does_not_need_login(self):
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        event = {'event': 'charge.success', 'data': self._success_payload(pay)}
        anon_status = [self._signed_webhook(event).status_code for _ in range(2)]
        self.assertEqual(anon_status, [200, 200])
        self.assertEqual(Payment.objects.filter(booking=self.booking, status=Payment.STATUS_PAID).count(), 1)

    def test_webhook_unknown_reference_is_ignored(self):
        res = self._signed_webhook({'event': 'charge.success', 'data': {
            'reference': 'nope', 'status': 'success', 'amount': 1, 'currency': 'KES'}})
        self.assertEqual(res.status_code, 200)

    def test_webhook_wrong_amount_not_marked_paid(self):
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        self._signed_webhook({'event': 'charge.success', 'data': self._success_payload(pay, amount=1)})
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.STATUS_PENDING)

    def test_webhook_get_not_allowed(self):
        self.assertEqual(self.client.get(self.webhook_url).status_code, 405)

    # ---- after payment ---------------------------------------------------
    def test_paid_booking_redirects_away_from_pay_page_and_shows_receipt(self):
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        self._signed_webhook({'event': 'charge.success', 'data': self._success_payload(pay)})
        res = self.client.get(reverse('core:pay_booking', args=[self.booking.id]))
        self.assertRedirects(res, reverse('core:booking_detail', args=[self.booking.id]))
        detail = self.client.get(reverse('core:booking_detail', args=[self.booking.id]))
        self.assertContains(detail, 'Paid')
        self.assertContains(detail, 'Mobile money')
        self.assertNotContains(detail, 'Pay Now')

    def test_paid_booking_cannot_be_initialized_again(self):
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        self._signed_webhook({'event': 'charge.success', 'data': self._success_payload(pay)})
        with patch('core.views.requests.post') as post:
            res = self.client.post(self.init_url, data='{}', content_type='application/json')
        self.assertTrue(res.json()['already_paid'])
        post.assert_not_called()

    def test_revenue_counts_paid_payments(self):
        staff = User.objects.create_user('staff1', password='x', is_staff=True)
        UserProfile.objects.create(user=staff, role='customer')
        self._initialize()
        pay = Payment.objects.get(booking=self.booking)
        self._signed_webhook({'event': 'charge.success', 'data': self._success_payload(pay)})
        c = Client()
        c.login(username='staff1', password='x')
        res = c.get(reverse('core:platform_totals'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['total_revenue'], Decimal('500.00'))
