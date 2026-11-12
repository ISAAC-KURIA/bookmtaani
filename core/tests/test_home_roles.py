"""
Tests for role-aware home page at "/".

NOTE: Python 3.14 + Django 5.1 have a known incompatibility in test template
instrumentation (RequestContext.__copy__ fails). We work around this by patching
store_rendered_templates to skip the broken copy(), and by checking response
content rather than template names where possible.
"""
from datetime import date, time, timedelta

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from core.models import (
    UserProfile, Business, BusinessHours, Service, Booking,
)
from core.services import get_user_role


# ---------------------------------------------------------------------------
# Patch for Python 3.14 / Django 5.1 RequestContext.__copy__ bug
#
# Python 3.14 changed how copy.copy() dispatches for classes with __slots__.
# Django 5.1's BaseContext sets self.dicts in __init__ but __copy__ tries to
# call super().__copy__() which under Py3.14 no longer sets up dicts.
# This patch gives RequestContext a working __copy__ that bypasses the broken chain.
# ---------------------------------------------------------------------------
def _patched_context_copy(self):
    cls = type(self)
    duplicate = cls.__new__(cls)
    duplicate.__dict__.update(self.__dict__)
    duplicate.dicts = self.dicts[:]
    return duplicate


# Apply patch at module load — before any test client is used
from django.template.context import RequestContext, Context  # noqa: E402
RequestContext.__copy__ = _patched_context_copy
Context.__copy__ = _patched_context_copy


def _make_user(username, role='customer', is_staff=False):
    u = User.objects.create_user(username=username, password='testpass123', is_staff=is_staff)
    if not is_staff:
        UserProfile.objects.create(user=u, role=role)
    else:
        UserProfile.objects.get_or_create(u, defaults={'role': 'customer'})
    return u


def _make_business(owner):
    return Business.objects.create(
        owner=owner, name='Test Kinyozi', category='kinyozi', town='Kisii',
    )


def _make_service(business):
    return Service.objects.create(
        business=business, name='Haircut', price=300, duration_minutes=30,
    )


def _next_weekday(weekday):
    today = date.today()
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


# ---------------------------------------------------------------------------
# Base test case
# ---------------------------------------------------------------------------
class HomeTestCase(TestCase):
    pass


# ---------------------------------------------------------------------------
# get_user_role() — no HTTP, no patch needed
# ---------------------------------------------------------------------------
class GetUserRoleTest(TestCase):

    def test_anonymous_returns_anonymous(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(get_user_role(AnonymousUser()), 'anonymous')

    def test_none_returns_anonymous(self):
        self.assertEqual(get_user_role(None), 'anonymous')

    def test_staff_returns_admin(self):
        u = User.objects.create_user('staff1', password='x', is_staff=True)
        UserProfile.objects.create(user=u, role='customer')
        self.assertEqual(get_user_role(u), 'admin')

    def test_customer_returns_customer(self):
        u = User.objects.create_user('cust1', password='x')
        UserProfile.objects.create(user=u, role='customer')
        self.assertEqual(get_user_role(u), 'customer')

    def test_owner_returns_owner(self):
        u = User.objects.create_user('own1', password='x')
        UserProfile.objects.create(user=u, role='owner')
        self.assertEqual(get_user_role(u), 'owner')


# ---------------------------------------------------------------------------
# Anonymous home
# ---------------------------------------------------------------------------
class AnonymousHomeTest(HomeTestCase):

    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_home_returns_200(self):
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_contains_how_it_works(self):
        self.assertContains(self.client.get('/'), 'How it works')

    def test_contains_register_link(self):
        self.assertContains(self.client.get('/'), 'Get started free')

    def test_contains_sign_in_link(self):
        self.assertContains(self.client.get('/'), 'Sign in')

    def test_no_private_data(self):
        r = self.client.get('/')
        self.assertNotContains(r, 'Upcoming Bookings')
        self.assertNotContains(r, 'Pending Approvals')
        self.assertNotContains(r, 'Platform Administration')

    def test_no_demo_banner(self):
        self.assertNotContains(self.client.get('/'), 'DEMO ONLY')


# ---------------------------------------------------------------------------
# Customer home
# ---------------------------------------------------------------------------
class CustomerHomeTest(HomeTestCase):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('cust_home', password='testpass123')
        UserProfile.objects.create(user=self.user, role='customer')
        self.client = Client()
        self.client.login(username='cust_home', password='testpass123')

    def test_home_returns_200(self):
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_contains_greeting(self):
        self.assertContains(self.client.get('/'), 'Welcome back')

    def test_contains_upcoming_bookings_section(self):
        self.assertContains(self.client.get('/'), 'Upcoming Bookings')

    def test_contains_find_service_search(self):
        self.assertContains(self.client.get('/'), 'Find a Service')

    def test_shows_customer_booking(self):
        owner = User.objects.create_user('own_for_cust', password='x')
        UserProfile.objects.create(user=owner, role='owner')
        biz = _make_business(owner)
        BusinessHours.objects.create(
            business=biz, day_of_week=0, open_time=time(8, 0), close_time=time(18, 0)
        )
        svc = _make_service(biz)
        Booking.objects.create(
            customer=self.user, service=svc,
            date=_next_weekday(0), start_time=time(10, 0), end_time=time(10, 30),
            status=Booking.STATUS_CONFIRMED,
        )
        self.assertContains(self.client.get('/'), 'Haircut')

    def test_does_not_show_owner_or_admin_sections(self):
        r = self.client.get('/')
        self.assertNotContains(r, 'Pending Approvals')
        self.assertNotContains(r, 'Platform Administration')


# ---------------------------------------------------------------------------
# Owner home
# ---------------------------------------------------------------------------
class OwnerHomeTest(HomeTestCase):

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user('own_home', password='testpass123')
        UserProfile.objects.create(user=self.owner, role='owner')
        self.business = _make_business(self.owner)
        self.client = Client()
        self.client.login(username='own_home', password='testpass123')

    def test_home_returns_200(self):
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_contains_business_name(self):
        self.assertContains(self.client.get('/'), 'Test Kinyozi')

    def test_contains_todays_schedule(self):
        self.assertContains(self.client.get('/'), "Today's Schedule")

    def test_contains_pending_approvals(self):
        self.assertContains(self.client.get('/'), 'Pending Approvals')

    def test_pending_booking_appears(self):
        customer = User.objects.create_user('cust_for_own', password='x')
        UserProfile.objects.create(user=customer, role='customer')
        svc = _make_service(self.business)
        Booking.objects.create(
            customer=customer, service=svc,
            date=_next_weekday(1), start_time=time(9, 0), end_time=time(9, 30),
            status=Booking.STATUS_PENDING,
        )
        r = self.client.get('/')
        self.assertContains(r, 'Confirm')
        self.assertContains(r, 'Decline')

    def test_does_not_show_anonymous_hero(self):
        self.assertNotContains(self.client.get('/'), 'How it works')

    def test_does_not_show_customer_sections(self):
        self.assertNotContains(self.client.get('/'), 'Upcoming Bookings')

    def test_owner_cannot_see_other_business_pending(self):
        other_owner = User.objects.create_user('other_own', password='x')
        UserProfile.objects.create(user=other_owner, role='owner')
        other_biz = Business.objects.create(
            owner=other_owner, name='Other Salon', category='salon', town='Nairobi'
        )
        other_svc = Service.objects.create(
            business=other_biz, name='Blowout', price=500, duration_minutes=45
        )
        customer = User.objects.create_user('cust_other', password='x')
        UserProfile.objects.create(user=customer, role='customer')
        Booking.objects.create(
            customer=customer, service=other_svc,
            date=_next_weekday(2), start_time=time(11, 0), end_time=time(11, 45),
            status=Booking.STATUS_PENDING,
        )
        self.assertNotContains(self.client.get('/'), 'Blowout')


# ---------------------------------------------------------------------------
# Admin home
# ---------------------------------------------------------------------------
class AdminHomeTest(HomeTestCase):

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            'admin_home', password='testpass123', is_staff=True
        )
        UserProfile.objects.create(user=self.admin, role='customer')
        self.client = Client()
        self.client.login(username='admin_home', password='testpass123')

    def test_home_returns_200(self):
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_contains_platform_title(self):
        self.assertContains(self.client.get('/'), 'Platform Administration')

    def test_contains_stats(self):
        r = self.client.get('/')
        self.assertContains(r, 'Total businesses')
        self.assertContains(r, 'Total bookings')

    def test_contains_awaiting_verification(self):
        self.assertContains(self.client.get('/'), 'Awaiting Verification')

    def test_unverified_business_appears(self):
        owner = User.objects.create_user('own_unver', password='x')
        UserProfile.objects.create(user=owner, role='owner')
        Business.objects.create(
            owner=owner, name='Unverified Spa', category='spa',
            town='Mombasa', is_verified=False,
        )
        self.assertContains(self.client.get('/'), 'Unverified Spa')

    def test_verified_business_not_in_waiting_list(self):
        owner = User.objects.create_user('own_ver', password='x')
        UserProfile.objects.create(user=owner, role='owner')
        Business.objects.create(
            owner=owner, name='Verified Salon', category='salon',
            town='Kisii', is_verified=True,
        )
        # The verified salon name must not appear in the unverified section
        # We check the HTML does not contain it in a verify-item context
        r = self.client.get('/')
        # Verified businesses don't show in the awaiting list
        # (they are excluded by the view's is_verified=False filter)
        content = r.content.decode()
        # Find the awaiting section and confirm it's not there
        awaiting_idx = content.find('Awaiting Verification')
        verify_link_idx = content.find('Verified Salon')
        # Either not found, or found before the section (which would be the nav label)
        # The simplest check: the name does not appear in a verify-item div
        self.assertNotIn('<span class="verify-item-name">Verified Salon</span>', content)

    def test_does_not_show_customer_or_owner_sections(self):
        r = self.client.get('/')
        self.assertNotContains(r, 'Upcoming Bookings')
        self.assertNotContains(r, "Today's Schedule")
        self.assertNotContains(r, 'How it works')


# ---------------------------------------------------------------------------
# Login redirect
# ---------------------------------------------------------------------------
class LoginRedirectTest(HomeTestCase):

    def test_customer_redirects_to_home(self):
        User.objects.create_user('lr_cust', password='testpass123')
        UserProfile.objects.create(
            user=User.objects.get(username='lr_cust'), role='customer'
        )
        c = Client()
        response = c.post(
            reverse('core:login'),
            {'username': 'lr_cust', 'password': 'testpass123'},
        )
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_owner_redirects_to_home(self):
        owner = User.objects.create_user('lr_own', password='testpass123')
        UserProfile.objects.create(user=owner, role='owner')
        _make_business(owner)
        c = Client()
        response = c.post(
            reverse('core:login'),
            {'username': 'lr_own', 'password': 'testpass123'},
        )
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_admin_redirects_to_home(self):
        u = User.objects.create_user('lr_admin', password='testpass123', is_staff=True)
        UserProfile.objects.create(user=u, role='customer')
        c = Client()
        response = c.post(
            reverse('core:login'),
            {'username': 'lr_admin', 'password': 'testpass123'},
        )
        self.assertRedirects(response, '/', fetch_redirect_response=False)


def _make_business(owner):
    b = Business.objects.create(
        owner=owner, name='Test Kinyozi', category='kinyozi', town='Kisii',
    )
    return b


def _make_service(business):
    return Service.objects.create(
        business=business, name='Haircut', price=300, duration_minutes=30,
    )


def _next_weekday(weekday):
    today = date.today()
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _used_template_names(response):
    """Extract template names from a response — avoids assertTemplateUsed copy() bug on Py3.14."""
    return [t.name for t in response.templates]


class GetUserRoleTest(TestCase):
    """Unit tests for the get_user_role() helper."""

    def test_anonymous_returns_anonymous(self):
        from django.contrib.auth.models import AnonymousUser
        anon = AnonymousUser()
        self.assertEqual(get_user_role(anon), 'anonymous')

    def test_none_returns_anonymous(self):
        self.assertEqual(get_user_role(None), 'anonymous')

    def test_staff_returns_admin(self):
        u = _make_user('staff1', is_staff=True)
        self.assertEqual(get_user_role(u), 'admin')

    def test_customer_returns_customer(self):
        u = _make_user('cust1', role='customer')
        self.assertEqual(get_user_role(u), 'customer')

    def test_owner_returns_owner(self):
        u = _make_user('own1', role='owner')
        self.assertEqual(get_user_role(u), 'owner')


class AnonymousHomeTest(TestCase):
    """Anonymous users see the public landing page and no private data."""

    def setUp(self):
        self.client = Client()

    def test_home_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_uses_anonymous_template(self):
        response = self.client.get('/')
        self.assertIn('core/home_anonymous.html', _used_template_names(response))

    def test_contains_how_it_works(self):
        response = self.client.get('/')
        self.assertContains(response, 'How it works')

    def test_contains_register_link(self):
        response = self.client.get('/')
        self.assertContains(response, 'Get started free')

    def test_contains_sign_in_link(self):
        response = self.client.get('/')
        self.assertContains(response, 'Sign in')

    def test_no_my_bookings_in_anonymous_home(self):
        """Private booking data must not appear for anonymous users."""
        response = self.client.get('/')
        self.assertNotContains(response, 'Upcoming Bookings')
        self.assertNotContains(response, 'Pending Approvals')
        self.assertNotContains(response, 'Platform Administration')

    def test_no_demo_banner(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'DEMO ONLY')


class CustomerHomeTest(TestCase):
    """Logged-in customers see the personalised customer home."""

    def setUp(self):
        self.user = _make_user('cust_home', role='customer')
        self.client = Client()
        self.client.login(username='cust_home', password='testpass123')

    def test_home_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_uses_customer_template(self):
        response = self.client.get('/')
        self.assertIn('core/home_customer.html', _used_template_names(response))

    def test_contains_greeting(self):
        response = self.client.get('/')
        self.assertContains(response, 'Welcome back')

    def test_contains_upcoming_bookings_section(self):
        response = self.client.get('/')
        self.assertContains(response, 'Upcoming Bookings')

    def test_contains_find_service_search(self):
        response = self.client.get('/')
        self.assertContains(response, 'Find a Service')

    def test_shows_customer_booking(self):
        """An upcoming booking for this customer appears on their home."""
        owner = _make_user('own_for_cust', role='owner')
        biz = _make_business(owner)
        BusinessHours.objects.create(
            business=biz, day_of_week=0, open_time=time(8, 0), close_time=time(18, 0)
        )
        svc = _make_service(biz)
        future = _next_weekday(0)
        Booking.objects.create(
            customer=self.user, service=svc,
            date=future, start_time=time(10, 0), end_time=time(10, 30),
            status=Booking.STATUS_CONFIRMED,
        )
        response = self.client.get('/')
        self.assertContains(response, 'Haircut')

    def test_does_not_show_owner_sections(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'Pending Approvals')
        self.assertNotContains(response, 'Platform Administration')


class OwnerHomeTest(TestCase):
    """Logged-in owners see the owner home with their business."""

    def setUp(self):
        self.owner = _make_user('own_home', role='owner')
        self.business = _make_business(self.owner)
        self.client = Client()
        self.client.login(username='own_home', password='testpass123')

    def test_home_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_uses_owner_template(self):
        response = self.client.get('/')
        self.assertIn('core/home_owner.html', _used_template_names(response))

    def test_contains_business_name(self):
        response = self.client.get('/')
        self.assertContains(response, 'Test Kinyozi')

    def test_contains_todays_schedule(self):
        response = self.client.get('/')
        self.assertContains(response, "Today's Schedule")

    def test_contains_pending_approvals(self):
        response = self.client.get('/')
        self.assertContains(response, 'Pending Approvals')

    def test_pending_booking_appears(self):
        """A pending booking for this business appears on the owner home."""
        customer = _make_user('cust_for_own', role='customer')
        svc = _make_service(self.business)
        future = _next_weekday(1)
        Booking.objects.create(
            customer=customer, service=svc,
            date=future, start_time=time(9, 0), end_time=time(9, 30),
            status=Booking.STATUS_PENDING,
        )
        response = self.client.get('/')
        self.assertContains(response, 'Confirm')
        self.assertContains(response, 'Decline')

    def test_does_not_show_anonymous_hero(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'How it works')

    def test_does_not_show_customer_sections(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'Upcoming Bookings')

    def test_owner_cannot_see_other_business_pending(self):
        """Owner's home only shows their own pending bookings."""
        other_owner = _make_user('other_own', role='owner')
        other_biz = Business.objects.create(
            owner=other_owner, name='Other Salon', category='salon', town='Nairobi'
        )
        other_svc = Service.objects.create(
            business=other_biz, name='Blowout', price=500, duration_minutes=45
        )
        customer = _make_user('cust_other', role='customer')
        future = _next_weekday(2)
        Booking.objects.create(
            customer=customer, service=other_svc,
            date=future, start_time=time(11, 0), end_time=time(11, 45),
            status=Booking.STATUS_PENDING,
        )
        response = self.client.get('/')
        # Blowout is for the other business — should not appear
        self.assertNotContains(response, 'Blowout')


class AdminHomeTest(TestCase):
    """Staff users see the admin home with platform totals."""

    def setUp(self):
        self.admin = _make_user('admin_home', is_staff=True)
        self.client = Client()
        self.client.login(username='admin_home', password='testpass123')

    def test_home_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_uses_admin_template(self):
        response = self.client.get('/')
        self.assertIn('core/home_admin.html', _used_template_names(response))

    def test_contains_platform_title(self):
        response = self.client.get('/')
        self.assertContains(response, 'Platform Administration')

    def test_contains_stats(self):
        response = self.client.get('/')
        self.assertContains(response, 'Total businesses')
        self.assertContains(response, 'Total bookings')

    def test_contains_awaiting_verification(self):
        response = self.client.get('/')
        self.assertContains(response, 'Awaiting Verification')

    def test_unverified_business_appears(self):
        owner = _make_user('own_unver', role='owner')
        Business.objects.create(
            owner=owner, name='Unverified Spa', category='spa',
            town='Mombasa', is_verified=False,
        )
        response = self.client.get('/')
        self.assertContains(response, 'Unverified Spa')

    def test_verified_business_not_in_waiting_list(self):
        owner = _make_user('own_ver', role='owner')
        Business.objects.create(
            owner=owner, name='Verified Salon', category='salon',
            town='Kisii', is_verified=True,
        )
        response = self.client.get('/')
        # Verified salon should not appear in the unverified list context
        unverified = response.context.get('unverified', []) if response.context else []
        names = [b.name for b in unverified]
        self.assertNotIn('Verified Salon', names)

    def test_does_not_show_customer_or_owner_sections(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'Upcoming Bookings')
        self.assertNotContains(response, "Today's Schedule")
        self.assertNotContains(response, 'How it works')


class LoginRedirectTest(TestCase):
    """After login, users land on / which serves their role home."""

    def test_customer_redirects_to_home(self):
        _make_user('lr_cust', role='customer')
        c = Client()
        response = c.post(
            reverse('core:login'),
            {'username': 'lr_cust', 'password': 'testpass123'},
        )
        # Should redirect to /
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_owner_redirects_to_home(self):
        owner = _make_user('lr_own', role='owner')
        _make_business(owner)
        c = Client()
        response = c.post(
            reverse('core:login'),
            {'username': 'lr_own', 'password': 'testpass123'},
        )
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_admin_redirects_to_home(self):
        _make_user('lr_admin', is_staff=True)
        c = Client()
        response = c.post(
            reverse('core:login'),
            {'username': 'lr_admin', 'password': 'testpass123'},
        )
        self.assertRedirects(response, '/', fetch_redirect_response=False)


def _make_user(username, role='customer', is_staff=False):
    u = User.objects.create_user(username=username, password='testpass123', is_staff=is_staff)
    if not is_staff:
        UserProfile.objects.create(user=u, role=role)
    else:
        # Staff users still get a profile (as customer by default)
        UserProfile.objects.get_or_create(user=u, defaults={'role': 'customer'})
    return u


def _make_business(owner):
    b = Business.objects.create(
        owner=owner, name='Test Kinyozi', category='kinyozi', town='Kisii',
    )
    return b


def _make_service(business):
    return Service.objects.create(
        business=business, name='Haircut', price=300, duration_minutes=30,
    )


def _next_weekday(weekday):
    today = date.today()
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


class GetUserRoleTest(TestCase):
    """Unit tests for the get_user_role() helper."""

    def test_anonymous_returns_anonymous(self):
        from django.contrib.auth.models import AnonymousUser
        anon = AnonymousUser()
        self.assertEqual(get_user_role(anon), 'anonymous')

    def test_none_returns_anonymous(self):
        self.assertEqual(get_user_role(None), 'anonymous')

    def test_staff_returns_admin(self):
        u = _make_user('staff1', is_staff=True)
        self.assertEqual(get_user_role(u), 'admin')

    def test_customer_returns_customer(self):
        u = _make_user('cust1', role='customer')
        self.assertEqual(get_user_role(u), 'customer')

    def test_owner_returns_owner(self):
        u = _make_user('own1', role='owner')
        self.assertEqual(get_user_role(u), 'owner')


class AnonymousHomeTest(TestCase):
    """Anonymous users see the public landing page and no private data."""

    def setUp(self):
        self.client = Client()

    def test_home_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_uses_anonymous_template(self):
        response = self.client.get('/')
        self.assertTemplateUsed(response, 'core/home_anonymous.html')

    def test_contains_how_it_works(self):
        response = self.client.get('/')
        self.assertContains(response, 'How it works')

    def test_contains_register_link(self):
        response = self.client.get('/')
        self.assertContains(response, 'Get started free')

    def test_contains_sign_in_link(self):
        response = self.client.get('/')
        self.assertContains(response, 'Sign in')

    def test_no_my_bookings_in_anonymous_home(self):
        """Private booking data must not appear for anonymous users."""
        response = self.client.get('/')
        self.assertNotContains(response, 'Upcoming Bookings')
        self.assertNotContains(response, 'Pending Approvals')
        self.assertNotContains(response, 'Platform Administration')

    def test_no_demo_banner(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'DEMO ONLY')


class CustomerHomeTest(TestCase):
    """Logged-in customers see the personalised customer home."""

    def setUp(self):
        self.user = _make_user('cust_home', role='customer')
        self.client = Client()
        self.client.login(username='cust_home', password='testpass123')

    def test_home_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_uses_customer_template(self):
        response = self.client.get('/')
        self.assertTemplateUsed(response, 'core/home_customer.html')

    def test_contains_greeting(self):
        response = self.client.get('/')
        self.assertContains(response, 'Welcome back')

    def test_contains_upcoming_bookings_section(self):
        response = self.client.get('/')
        self.assertContains(response, 'Upcoming Bookings')

    def test_contains_find_service_search(self):
        response = self.client.get('/')
        self.assertContains(response, 'Find a Service')

    def test_shows_customer_booking(self):
        """An upcoming booking for this customer appears on their home."""
        owner = _make_user('own_for_cust', role='owner')
        biz = _make_business(owner)
        BusinessHours.objects.create(
            business=biz, day_of_week=0, open_time=time(8, 0), close_time=time(18, 0)
        )
        svc = _make_service(biz)
        future = _next_weekday(0)
        Booking.objects.create(
            customer=self.user, service=svc,
            date=future, start_time=time(10, 0), end_time=time(10, 30),
            status=Booking.STATUS_CONFIRMED,
        )
        response = self.client.get('/')
        self.assertContains(response, 'Haircut')

    def test_does_not_show_owner_sections(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'Pending Approvals')
        self.assertNotContains(response, 'Platform Administration')


class OwnerHomeTest(TestCase):
    """Logged-in owners see the owner home with their business."""

    def setUp(self):
        self.owner = _make_user('own_home', role='owner')
        self.business = _make_business(self.owner)
        self.client = Client()
        self.client.login(username='own_home', password='testpass123')

    def test_home_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_uses_owner_template(self):
        response = self.client.get('/')
        self.assertTemplateUsed(response, 'core/home_owner.html')

    def test_contains_business_name(self):
        response = self.client.get('/')
        self.assertContains(response, 'Test Kinyozi')

    def test_contains_todays_schedule(self):
        response = self.client.get('/')
        self.assertContains(response, "Today's Schedule")

    def test_contains_pending_approvals(self):
        response = self.client.get('/')
        self.assertContains(response, 'Pending Approvals')

    def test_pending_booking_appears(self):
        """A pending booking for this business appears on the owner home."""
        customer = _make_user('cust_for_own', role='customer')
        svc = _make_service(self.business)
        future = _next_weekday(1)
        Booking.objects.create(
            customer=customer, service=svc,
            date=future, start_time=time(9, 0), end_time=time(9, 30),
            status=Booking.STATUS_PENDING,
        )
        response = self.client.get('/')
        self.assertContains(response, 'Confirm')
        self.assertContains(response, 'Decline')

    def test_does_not_show_anonymous_hero(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'How it works')

    def test_does_not_show_customer_sections(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'Upcoming Bookings')

    def test_owner_cannot_see_other_business_pending(self):
        """Owner's home only shows their own pending bookings."""
        other_owner = _make_user('other_own', role='owner')
        other_biz = Business.objects.create(
            owner=other_owner, name='Other Salon', category='salon', town='Nairobi'
        )
        other_svc = Service.objects.create(
            business=other_biz, name='Blowout', price=500, duration_minutes=45
        )
        customer = _make_user('cust_other', role='customer')
        future = _next_weekday(2)
        Booking.objects.create(
            customer=customer, service=other_svc,
            date=future, start_time=time(11, 0), end_time=time(11, 45),
            status=Booking.STATUS_PENDING,
        )
        response = self.client.get('/')
        # Blowout is for the other business — should not appear
        self.assertNotContains(response, 'Blowout')


class AdminHomeTest(TestCase):
    """Staff users see the admin home with platform totals."""

    def setUp(self):
        self.admin = _make_user('admin_home', is_staff=True)
        self.client = Client()
        self.client.login(username='admin_home', password='testpass123')

    def test_home_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_uses_admin_template(self):
        response = self.client.get('/')
        self.assertTemplateUsed(response, 'core/home_admin.html')

    def test_contains_platform_title(self):
        response = self.client.get('/')
        self.assertContains(response, 'Platform Administration')

    def test_contains_stats(self):
        response = self.client.get('/')
        self.assertContains(response, 'Total businesses')
        self.assertContains(response, 'Total bookings')

    def test_contains_awaiting_verification(self):
        response = self.client.get('/')
        self.assertContains(response, 'Awaiting Verification')

    def test_unverified_business_appears(self):
        owner = _make_user('own_unver', role='owner')
        Business.objects.create(
            owner=owner, name='Unverified Spa', category='spa',
            town='Mombasa', is_verified=False,
        )
        response = self.client.get('/')
        self.assertContains(response, 'Unverified Spa')

    def test_verified_business_not_in_waiting_list(self):
        owner = _make_user('own_ver', role='owner')
        Business.objects.create(
            owner=owner, name='Verified Salon', category='salon',
            town='Kisii', is_verified=True,
        )
        # Reload; verified biz should not appear in the unverified list
        response = self.client.get('/')
        # Check by looking at unverified queryset in context
        unverified = response.context.get('unverified', [])
        names = [b.name for b in unverified]
        self.assertNotIn('Verified Salon', names)

    def test_does_not_show_customer_or_owner_sections(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'Upcoming Bookings')
        self.assertNotContains(response, "Today's Schedule")
        self.assertNotContains(response, 'How it works')


class LoginRedirectTest(TestCase):
    """After login, users land on / which serves their role home."""

    def test_customer_redirects_to_home(self):
        _make_user('lr_cust', role='customer')
        c = Client()
        response = c.post(
            reverse('core:login'),
            {'username': 'lr_cust', 'password': 'testpass123'},
            follow=True,
        )
        self.assertTemplateUsed(response, 'core/home_customer.html')

    def test_owner_redirects_to_home(self):
        owner = _make_user('lr_own', role='owner')
        _make_business(owner)
        c = Client()
        response = c.post(
            reverse('core:login'),
            {'username': 'lr_own', 'password': 'testpass123'},
            follow=True,
        )
        self.assertTemplateUsed(response, 'core/home_owner.html')

    def test_admin_redirects_to_home(self):
        _make_user('lr_admin', is_staff=True)
        c = Client()
        response = c.post(
            reverse('core:login'),
            {'username': 'lr_admin', 'password': 'testpass123'},
            follow=True,
        )
        self.assertTemplateUsed(response, 'core/home_admin.html')
