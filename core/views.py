import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, date, timedelta
from collections import defaultdict
from decimal import Decimal

import requests

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.db import transaction
from django.db.models import Count, Sum, Avg, Q
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import (
    UserProfile, Business, BusinessHours, Service, TimeBlock,
    Booking, Payment, SMSNotification, Review, CustomerNote,
)
from .forms import (
    RegisterForm, BookingDateForm, ServiceForm, TimeBlockForm,
    BusinessHoursForm, ReviewForm, CustomerNoteForm, BusinessProfileForm,
)
from .services import get_available_slots, create_booking, create_sms_notifications, get_user_role

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_owner(user):
    """Return (business, None) if user is owner with a business, else (None, redirect)."""
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        return None, redirect('core:home')
    if not profile.is_owner:
        return None, HttpResponseForbidden("Owner access required.")
    business = Business.objects.filter(owner=user).first()
    return business, None


def _get_or_404_owner_business(user):
    try:
        profile = user.profile
        if not profile.is_owner:
            return None
    except UserProfile.DoesNotExist:
        return None
    return Business.objects.filter(owner=user).first()


# ---------------------------------------------------------------------------
# Public views
# ---------------------------------------------------------------------------

def _search_businesses(request):
    """Shared business search logic used across home page variants."""
    businesses = Business.objects.prefetch_related('services')
    category = request.GET.get('category', '')
    town = request.GET.get('town', '')
    search = request.GET.get('search', '')
    if category:
        businesses = businesses.filter(category=category)
    if town:
        businesses = businesses.filter(town__icontains=town)
    if search:
        businesses = businesses.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )
    towns = Business.objects.values_list('town', flat=True).distinct().order_by('town')
    return businesses, {
        'businesses': businesses,
        'categories': Business.CATEGORY_CHOICES,
        'towns': towns,
        'selected_category': category,
        'selected_town': town,
        'search_query': search,
    }


def home(request):
    role = get_user_role(request.user)

    if role == 'admin':
        return _home_admin(request)
    elif role == 'owner':
        return _home_owner(request)
    elif role == 'customer':
        return _home_customer(request)
    else:
        return _home_anonymous(request)


def _home_anonymous(request):
    """Landing page for visitors who are not logged in."""
    businesses, search_ctx = _search_businesses(request)
    context = {**search_ctx, 'role': 'anonymous'}
    return render(request, 'core/home_anonymous.html', context)


def _home_customer(request):
    """Personalised home for logged-in customers."""
    today = timezone.localtime(timezone.now()).date()

    # Next 3 upcoming bookings
    upcoming = (
        Booking.objects.filter(
            customer=request.user,
            date__gte=today,
            status__in=(Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED),
        )
        .select_related('service__business')
        .order_by('date', 'start_time')[:3]
    )

    # Recently booked businesses (last 5 distinct, most recent first)
    recent_business_ids = (
        Booking.objects.filter(customer=request.user)
        .exclude(status=Booking.STATUS_CANCELLED)
        .order_by('-created_at')
        .values_list('service__business_id', flat=True)
    )
    seen = []
    for bid in recent_business_ids:
        if bid not in seen:
            seen.append(bid)
        if len(seen) >= 5:
            break
    recent_businesses = []
    for bid in seen:
        try:
            recent_businesses.append(Business.objects.get(pk=bid))
        except Business.DoesNotExist:
            pass

    # Recent simulated SMS notifications (last 5)
    recent_notifications = (
        SMSNotification.objects.filter(booking__customer=request.user)
        .select_related('booking__service__business')
        .order_by('-scheduled_at')[:5]
    )

    businesses, search_ctx = _search_businesses(request)
    context = {
        **search_ctx,
        'role': 'customer',
        'upcoming': upcoming,
        'recent_businesses': recent_businesses,
        'recent_notifications': recent_notifications,
    }
    return render(request, 'core/home_customer.html', context)


def _home_owner(request):
    """Owner home: today's schedule + pending approvals + this week summary."""
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        from django.contrib import messages as _messages
        _messages.info(request, "You haven't registered a business yet.")
        return redirect('core:owner_register_business')

    today = timezone.localtime(timezone.now()).date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    todays_bookings = (
        Booking.objects.filter(
            service__business=business,
            date=today,
            status__in=(Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED),
        )
        .select_related('customer', 'service')
        .order_by('start_time')
    )

    pending_bookings = (
        Booking.objects.filter(
            service__business=business,
            status=Booking.STATUS_PENDING,
        )
        .select_related('customer', 'service')
        .order_by('date', 'start_time')[:10]
    )

    week_bookings_count = Booking.objects.filter(
        service__business=business,
        date__gte=week_start,
        date__lte=week_end,
        status__in=(Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED),
    ).count()

    week_revenue = Booking.objects.filter(
        service__business=business,
        date__gte=week_start,
        date__lte=week_end,
        status__in=(Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED),
    ).aggregate(total=Sum('service__price'))['total'] or 0

    context = {
        'role': 'owner',
        'business': business,
        'todays_bookings': todays_bookings,
        'pending_bookings': pending_bookings,
        'week_bookings_count': week_bookings_count,
        'week_revenue': week_revenue,
        'today': today,
    }
    return render(request, 'core/home_owner.html', context)


def _home_admin(request):
    """Admin home: platform totals + businesses awaiting verification."""
    total_businesses = Business.objects.count()
    total_bookings = Booking.objects.count()
    verified_businesses = Business.objects.filter(is_verified=True).count()
    total_revenue = Payment.objects.filter(
        status__in=Payment.PAID_STATUSES
    ).aggregate(total=Sum('amount'))['total'] or 0

    unverified = Business.objects.filter(is_verified=False).order_by('name')[:20]

    context = {
        'role': 'admin',
        'total_businesses': total_businesses,
        'total_bookings': total_bookings,
        'verified_businesses': verified_businesses,
        'total_revenue': total_revenue,
        'unverified': unverified,
    }
    return render(request, 'core/home_admin.html', context)


def business_detail(request, slug):
    business = get_object_or_404(Business, slug=slug)
    services = business.services.filter(is_active=True)
    hours = business.hours.all()
    reviews = Review.objects.filter(booking__service__business=business).select_related(
        'booking__customer'
    ).order_by('-created_at')[:20]
    avg_rating = business.average_rating()
    review_count = business.review_count()

    context = {
        'business': business,
        'services': services,
        'hours': hours,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'review_count': review_count,
        'day_names': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    }
    return render(request, 'core/business_detail.html', context)


# ---------------------------------------------------------------------------
# Auth views
# ---------------------------------------------------------------------------

def login_view(request):
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get('next', '/')
            return redirect(next_url)
        else:
            error = "Invalid username or password."
    return render(request, 'registration/login.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('core:home')


def register_view(request):
    form = RegisterForm()
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            user = User.objects.create_user(
                username=cd['username'],
                email=cd.get('email', ''),
                password=cd['password1'],
            )
            if cd.get('full_name'):
                parts = cd['full_name'].split(' ', 1)
                user.first_name = parts[0]
                user.last_name = parts[1] if len(parts) > 1 else ''
                user.save()
            UserProfile.objects.create(user=user, role=cd['role'])
            login(request, user)
            messages.success(request, f"Welcome, {user.username}! Your account has been created.")
            if cd['role'] == 'owner':
                return redirect('core:owner_register_business')
            return redirect('core:home')
    return render(request, 'registration/register.html', {'form': form})


# ---------------------------------------------------------------------------
# Booking flow
# ---------------------------------------------------------------------------

@login_required
def booking_form(request, service_id):
    service = get_object_or_404(Service, id=service_id, is_active=True)
    form = BookingDateForm(request.GET or None)
    selected_date = None
    slots = []

    if form.is_valid():
        selected_date = form.cleaned_data['date']
        slots = get_available_slots(service, selected_date)

    context = {
        'service': service,
        'business': service.business,
        'form': form,
        'selected_date': selected_date,
        'slots': slots,
    }
    return render(request, 'core/booking_form.html', context)


@login_required
def available_slots_json(request, service_id):
    service = get_object_or_404(Service, id=service_id, is_active=True)
    date_str = request.GET.get('date', '')
    try:
        booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date'}, status=400)
    slots = get_available_slots(service, booking_date)
    return JsonResponse({'slots': slots, 'date': date_str})


@login_required
def booking_confirm(request, service_id, date, time):
    service = get_object_or_404(Service, id=service_id, is_active=True)
    try:
        booking_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, "Invalid date.")
        return redirect('core:booking_form', service_id=service_id)

    # Verify slot is still available
    slots = get_available_slots(service, booking_date)
    if time not in slots:
        messages.error(request, "That slot is no longer available. Please choose another time.")
        return redirect('core:booking_form', service_id=service_id)

    if request.method == 'POST':
        try:
            booking = create_booking(request.user, service, booking_date, time)
            create_sms_notifications(booking)
            messages.success(request, "Booking created! Complete your payment to confirm it.")
            pay_url = reverse('core:pay_booking', args=[booking.id])
            return redirect(f"{pay_url}?autopay=1")
        except ValidationError as e:
            messages.error(request, str(e.message))
            return redirect('core:booking_form', service_id=service_id)

    end_time = (datetime.combine(booking_date, datetime.strptime(time, '%H:%M').time())
                + timedelta(minutes=service.duration_minutes)).time()

    context = {
        'service': service,
        'business': service.business,
        'booking_date': booking_date,
        'start_time': time,
        'end_time': end_time.strftime('%H:%M'),
    }
    return render(request, 'core/booking_confirm.html', context)


# ---------------------------------------------------------------------------
# Paystack payments
#
# Flow:
#   1. pay_booking          - page with the Pay button
#   2. paystack_initialize  - (AJAX) server starts the transaction, returns access_code
#   3. Browser opens the Paystack popup with that access_code
#   4. paystack_verify      - (AJAX) after the popup reports success, server re-checks
#                             the transaction with Paystack before marking it paid
#   5. paystack_webhook     - Paystack calls this itself, so payments are recorded even
#                             if the customer closes the tab before step 4
# ---------------------------------------------------------------------------

PAYABLE_BOOKING_STATUSES = (Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED)
PAYSTACK_TIMEOUT = 20  # seconds


def _paystack_configured():
    key = settings.PAYSTACK_SECRET_KEY or ''
    return key.startswith(('sk_test_', 'sk_live_')) and 'REPLACE' not in key


def _paystack_headers():
    return {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }


def _to_subunit(amount):
    """KES 500.00 -> 50000 (Paystack expects the smallest currency unit)."""
    return int((Decimal(amount) * 100).to_integral_value())


def _paystack_verify(reference):
    """Ask Paystack for the real status of a transaction. Returns its data dict, or None."""
    try:
        res = requests.get(
            f"{settings.PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=_paystack_headers(),
            timeout=PAYSTACK_TIMEOUT,
        )
        body = res.json()
    except (requests.RequestException, ValueError):
        logger.exception("Paystack verify failed for %s", reference)
        return None
    if not body.get('status'):
        return None
    return body.get('data') or {}


def _settle_payment(payment_id, data):
    """
    Apply a Paystack transaction payload to our Payment record.
    Safe to call repeatedly (webhook + verify can both arrive).
    Returns 'paid', 'failed', 'pending' or 'mismatch'.
    """
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related('booking').get(pk=payment_id)

        if payment.status == Payment.STATUS_PAID:
            return 'paid'

        tx_status = data.get('status')

        if tx_status == 'success':
            currency = str(data.get('currency', '')).upper()
            if data.get('amount') != _to_subunit(payment.amount) or currency != settings.PAYSTACK_CURRENCY.upper():
                # Money arrived but not the amount/currency we expected - never auto-confirm.
                logger.error(
                    "Paystack amount/currency mismatch for %s: got %s %s, expected %s %s",
                    payment.transaction_ref, data.get('amount'), currency,
                    _to_subunit(payment.amount), settings.PAYSTACK_CURRENCY,
                )
                return 'mismatch'

            payment.status = Payment.STATUS_PAID
            payment.channel = data.get('channel') or ''
            payment.paid_at = timezone.now()
            payment.save(update_fields=['status', 'channel', 'paid_at'])

            booking = payment.booking
            if booking.status == Booking.STATUS_PENDING:
                booking.status = Booking.STATUS_CONFIRMED
                booking.save(update_fields=['status'])
            return 'paid'

        if tx_status in ('failed', 'abandoned', 'reversed'):
            payment.status = Payment.STATUS_DECLINED
            payment.save(update_fields=['status'])
            return 'failed'

        return 'pending'


def _can_pay(booking, payment):
    if payment and payment.is_paid:
        return False
    return booking.status in PAYABLE_BOOKING_STATUSES


@login_required
def pay_booking(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related('service__business'),
        id=booking_id, customer=request.user,
    )
    payment = Payment.objects.filter(booking=booking).first()

    # Already paid?
    if payment and payment.is_paid:
        return redirect('core:booking_detail', booking_id=booking.id)

    if not _can_pay(booking, payment):
        messages.error(request, "This booking can no longer be paid for.")
        return redirect('core:booking_detail', booking_id=booking.id)

    email = request.user.email
    config = {
        'initUrl': reverse('core:paystack_initialize', args=[booking.id]),
        'verifyUrl': reverse('core:paystack_verify', args=[booking.id]),
        'detailUrl': reverse('core:booking_detail', args=[booking.id]),
        # Open the popup straight away when we arrive from "Confirm Booking & Pay"
        # (only possible if we already have an email to send to Paystack).
        'autopay': request.GET.get('autopay') == '1' and bool(email),
    }
    context = {
        'booking': booking,
        'user_email': email,
        'pay_config': config,
    }
    return render(request, 'core/paystack_payment.html', context)


@login_required
@require_POST
def paystack_initialize(request, booking_id):
    """Create the Paystack transaction on the server and hand the access_code to the browser."""
    booking = get_object_or_404(
        Booking.objects.select_related('service__business'),
        id=booking_id, customer=request.user,
    )
    detail_url = reverse('core:booking_detail', args=[booking.id])
    payment = Payment.objects.filter(booking=booking).first()

    if payment and payment.is_paid:
        return JsonResponse({'already_paid': True, 'redirect': detail_url})

    if booking.status not in PAYABLE_BOOKING_STATUSES:
        return JsonResponse({'error': 'This booking can no longer be paid for.'}, status=409)

    if not _paystack_configured():
        return JsonResponse(
            {'error': 'Paystack is not configured yet. Add your Paystack keys in settings.py.'},
            status=503,
        )

    try:
        body = json.loads(request.body or b'{}')
    except ValueError:
        body = {}
    email = (body.get('email') or request.user.email or '').strip()
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'error': 'Enter a valid email address.', 'field': 'email'}, status=400)

    # If an earlier attempt exists, check whether it actually went through before starting a new one.
    if payment and payment.method == 'paystack' and payment.transaction_ref:
        previous = _paystack_verify(payment.transaction_ref)
        if previous and _settle_payment(payment.id, previous) == 'paid':
            return JsonResponse({'already_paid': True, 'redirect': detail_url})

    amount = booking.service.price            # always taken from the database, never from the browser
    reference = f"BM{booking.id}-{uuid.uuid4().hex[:12]}"

    payload = {
        'email': email,
        'amount': _to_subunit(amount),
        'currency': settings.PAYSTACK_CURRENCY,
        'reference': reference,
        'metadata': {
            'booking_id': booking.id,
            'custom_fields': [
                {'display_name': 'Business', 'variable_name': 'business',
                 'value': booking.service.business.name},
                {'display_name': 'Service', 'variable_name': 'service',
                 'value': booking.service.name},
                {'display_name': 'Booking', 'variable_name': 'booking_id',
                 'value': str(booking.id)},
            ],
        },
    }

    try:
        res = requests.post(
            f"{settings.PAYSTACK_BASE_URL}/transaction/initialize",
            headers=_paystack_headers(),
            json=payload,
            timeout=PAYSTACK_TIMEOUT,
        )
        result = res.json()
    except (requests.RequestException, ValueError):
        logger.exception("Paystack initialize failed for booking %s", booking.id)
        return JsonResponse(
            {'error': 'Could not reach Paystack. Please try again in a moment.'}, status=502,
        )

    if not result.get('status'):
        logger.error("Paystack initialize rejected for booking %s: %s", booking.id, result.get('message'))
        return JsonResponse(
            {'error': result.get('message') or 'Paystack could not start this payment.'}, status=502,
        )

    Payment.objects.update_or_create(
        booking=booking,
        defaults={
            'amount': amount,
            'method': 'paystack',
            'status': Payment.STATUS_PENDING,
            'transaction_ref': reference,
            'channel': '',
            'paid_at': None,
        },
    )
    return JsonResponse({
        'access_code': result['data']['access_code'],
        'reference': reference,
    })


@login_required
@require_POST
def paystack_verify(request, booking_id):
    """Called by the browser after the popup reports success. Paystack, not the browser, decides."""
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    detail_url = reverse('core:booking_detail', args=[booking.id])
    payment = Payment.objects.filter(booking=booking, method='paystack').first()
    if not payment or not payment.transaction_ref:
        return JsonResponse({'status': 'error', 'error': 'No payment was started for this booking.'}, status=404)

    data = _paystack_verify(payment.transaction_ref)
    if data is None:
        return JsonResponse(
            {'status': 'error', 'error': 'Could not confirm the payment with Paystack yet.'}, status=502,
        )

    result = _settle_payment(payment.id, data)
    return JsonResponse({'status': result, 'redirect': detail_url})


@csrf_exempt
@require_POST
def paystack_webhook(request):
    """Server-to-server notification from Paystack. Authenticated by its HMAC signature."""
    signature = request.headers.get('x-paystack-signature', '')
    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode(), request.body, hashlib.sha512,
    ).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        return HttpResponse(status=401)

    try:
        event = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)

    if event.get('event') == 'charge.success':
        data = event.get('data') or {}
        reference = data.get('reference', '')
        payment = Payment.objects.filter(transaction_ref=reference).first()
        if payment:
            _settle_payment(payment.id, data)
        else:
            logger.warning("Paystack webhook for unknown reference %s", reference)

    return HttpResponse(status=200)


@login_required
def booking_detail(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    sms_notifications = booking.sms_notifications.all()
    payment = getattr(booking, 'payment', None)
    review = getattr(booking, 'review', None)

    context = {
        'booking': booking,
        'payment': payment,
        'can_pay': _can_pay(booking, payment),
        'sms_notifications': sms_notifications,
        'review': review,
    }
    return render(request, 'core/booking_detail.html', context)


# ---------------------------------------------------------------------------
# Customer views
# ---------------------------------------------------------------------------

@login_required
def my_bookings(request):
    today = timezone.localtime(timezone.now()).date()
    upcoming = Booking.objects.filter(
        customer=request.user,
        date__gte=today,
        status__in=(Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED),
    ).select_related('service__business').order_by('date', 'start_time')

    past = Booking.objects.filter(
        customer=request.user,
    ).exclude(
        Q(date__gte=today, status__in=(Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED))
    ).select_related('service__business').order_by('-date', '-start_time')

    context = {
        'upcoming': upcoming,
        'past': past,
    }
    return render(request, 'core/my_bookings.html', context)


@login_required
@require_POST
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    if booking.can_cancel():
        booking.status = Booking.STATUS_CANCELLED
        booking.save()
        messages.success(request, "Booking cancelled.")
    else:
        messages.error(request, "This booking cannot be cancelled.")
    return redirect('core:my_bookings')


@login_required
def reschedule_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    if not booking.can_cancel():
        messages.error(request, "This booking cannot be rescheduled.")
        return redirect('core:my_bookings')

    service = booking.service
    form = BookingDateForm(request.GET or None)
    slots = []
    selected_date = None

    if form.is_valid():
        selected_date = form.cleaned_data['date']
        slots = get_available_slots(service, selected_date)

    if request.method == 'POST' and 'time' in request.POST:
        date_str = request.POST.get('date', '')
        time_str = request.POST.get('time', '')
        try:
            new_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid date.")
            return redirect('core:reschedule_booking', booking_id=booking_id)
        try:
            new_booking = create_booking(request.user, service, new_date, time_str)
            create_sms_notifications(new_booking)
            booking.status = Booking.STATUS_CANCELLED
            booking.save()
            messages.success(request, "Booking rescheduled successfully!")
            return redirect('core:booking_detail', booking_id=new_booking.id)
        except ValidationError as e:
            messages.error(request, str(e.message))

    context = {
        'booking': booking,
        'service': service,
        'form': form,
        'slots': slots,
        'selected_date': selected_date,
    }
    return render(request, 'core/reschedule_booking.html', context)


@login_required
def notifications(request):
    notifications_qs = SMSNotification.objects.filter(
        booking__customer=request.user
    ).select_related('booking__service__business').order_by('-scheduled_at')
    return render(request, 'core/notifications.html', {'notifications': notifications_qs})


@login_required
def submit_review(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    if booking.status != Booking.STATUS_COMPLETED:
        messages.error(request, "You can only review completed bookings.")
        return redirect('core:my_bookings')
    if hasattr(booking, 'review'):
        messages.info(request, "You have already reviewed this booking.")
        return redirect('core:booking_detail', booking_id=booking_id)

    form = ReviewForm()
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.booking = booking
            review.save()
            messages.success(request, "Thank you for your review!")
            return redirect('core:booking_detail', booking_id=booking_id)

    return render(request, 'core/submit_review.html', {'form': form, 'booking': booking})


# ---------------------------------------------------------------------------
# Owner views
# ---------------------------------------------------------------------------

@login_required
def owner_dashboard(request):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        messages.info(request, "You haven't registered a business yet.")
        return redirect('core:owner_register_business')

    today = timezone.localtime(timezone.now()).date()
    todays_bookings = Booking.objects.filter(
        service__business=business,
        date=today,
        status__in=(Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED),
    ).select_related('customer', 'service').order_by('start_time')

    pending_count = Booking.objects.filter(
        service__business=business,
        status=Booking.STATUS_PENDING,
    ).count()

    context = {
        'business': business,
        'todays_bookings': todays_bookings,
        'pending_count': pending_count,
        'today': today,
    }
    return render(request, 'core/owner_dashboard.html', context)


@login_required
def owner_bookings(request):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    status_filter = request.GET.get('status', '')
    bookings = Booking.objects.filter(
        service__business=business,
    ).select_related('customer', 'service').order_by('-date', '-start_time')

    if status_filter:
        bookings = bookings.filter(status=status_filter)

    context = {
        'business': business,
        'bookings': bookings,
        'status_filter': status_filter,
        'status_choices': Booking.STATUS_CHOICES,
    }
    return render(request, 'core/owner_bookings.html', context)


@login_required
@require_POST
def owner_booking_action(request, booking_id):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    booking = get_object_or_404(Booking, id=booking_id, service__business=business)
    action = request.POST.get('action', '')

    action_map = {
        'confirm': Booking.STATUS_CONFIRMED,
        'complete': Booking.STATUS_COMPLETED,
        'cancel': Booking.STATUS_CANCELLED,
        'no_show': Booking.STATUS_NO_SHOW,
    }
    if action in action_map:
        booking.status = action_map[action]
        booking.save()
        messages.success(request, f"Booking marked as {booking.get_status_display()}.")
    else:
        messages.error(request, "Invalid action.")

    return redirect('core:owner_bookings')


@login_required
def owner_services(request):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    services = business.services.all()
    context = {'business': business, 'services': services}
    return render(request, 'core/owner_services.html', context)


@login_required
def owner_service_add(request):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    form = ServiceForm()
    if request.method == 'POST':
        form = ServiceForm(request.POST)
        if form.is_valid():
            service = form.save(commit=False)
            service.business = business
            service.save()
            messages.success(request, "Service added.")
            return redirect('core:owner_services')

    return render(request, 'core/owner_service_form.html', {
        'form': form, 'business': business, 'action': 'Add'
    })


@login_required
def owner_service_edit(request, service_id):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    service = get_object_or_404(Service, id=service_id, business=business)
    form = ServiceForm(instance=service)
    if request.method == 'POST':
        form = ServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, "Service updated.")
            return redirect('core:owner_services')

    return render(request, 'core/owner_service_form.html', {
        'form': form, 'business': business, 'action': 'Edit'
    })


@login_required
@require_POST
def owner_service_delete(request, service_id):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    service = get_object_or_404(Service, id=service_id, business=business)
    service.delete()
    messages.success(request, "Service deleted.")
    return redirect('core:owner_services')


@login_required
def owner_schedule(request):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    today = timezone.localtime(timezone.now()).date()
    upcoming_blocks = TimeBlock.objects.filter(
        business=business, date__gte=today
    ).order_by('date', 'start_time')

    context = {
        'business': business,
        'upcoming_blocks': upcoming_blocks,
        'today': today,
    }
    return render(request, 'core/owner_schedule.html', context)


@login_required
def owner_block_add(request):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    form = TimeBlockForm()
    if request.method == 'POST':
        form = TimeBlockForm(request.POST)
        if form.is_valid():
            block = form.save(commit=False)
            block.business = business
            block.save()
            messages.success(request, "Time block added.")
            return redirect('core:owner_schedule')

    return render(request, 'core/owner_block_form.html', {'form': form, 'business': business})


@login_required
@require_POST
def owner_block_delete(request, block_id):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    block = get_object_or_404(TimeBlock, id=block_id, business=business)
    block.delete()
    messages.success(request, "Time block removed.")
    return redirect('core:owner_schedule')


@login_required
def owner_hours(request):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    form = BusinessHoursForm(business=business)
    if request.method == 'POST':
        form = BusinessHoursForm(request.POST, business=business)
        if form.is_valid():
            cd = form.cleaned_data
            for day in range(7):
                prefix = f'day_{day}'
                is_closed = cd.get(f'{prefix}_is_closed', False)
                open_t = cd.get(f'{prefix}_open')
                close_t = cd.get(f'{prefix}_close')
                BusinessHours.objects.update_or_create(
                    business=business,
                    day_of_week=day,
                    defaults={
                        'is_closed': is_closed,
                        'open_time': None if is_closed else open_t,
                        'close_time': None if is_closed else close_t,
                    },
                )
            messages.success(request, "Business hours updated.")
            return redirect('core:owner_dashboard')

    return render(request, 'core/owner_hours.html', {
        'form': form, 'business': business,
        'days': [(i, n) for i, n in enumerate(['Monday', 'Tuesday', 'Wednesday',
                                               'Thursday', 'Friday', 'Saturday', 'Sunday'])]
    })


@login_required
def owner_customers(request):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    # Get all customers who booked this business
    customer_data = []
    customer_ids = Booking.objects.filter(
        service__business=business,
    ).values_list('customer_id', flat=True).distinct()

    for cust_id in customer_ids:
        cust = User.objects.get(id=cust_id)
        bookings = Booking.objects.filter(service__business=business, customer=cust)
        visit_count = bookings.exclude(status=Booking.STATUS_CANCELLED).count()
        total_spend = bookings.filter(
            status__in=(Booking.STATUS_COMPLETED, Booking.STATUS_CONFIRMED)
        ).aggregate(total=Sum('service__price'))['total'] or 0
        note_obj = CustomerNote.objects.filter(business=business, customer=cust).first()
        customer_data.append({
            'customer': cust,
            'visit_count': visit_count,
            'total_spend': total_spend,
            'note': note_obj,
        })

    context = {'business': business, 'customer_data': customer_data}
    return render(request, 'core/owner_customers.html', context)


@login_required
def owner_customer_note(request, customer_id):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    customer = get_object_or_404(User, id=customer_id)
    note_obj, _ = CustomerNote.objects.get_or_create(business=business, customer=customer,
                                                      defaults={'note': ''})
    form = CustomerNoteForm(instance=note_obj)
    if request.method == 'POST':
        form = CustomerNoteForm(request.POST, instance=note_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Note saved.")
            return redirect('core:owner_customers')

    return render(request, 'core/owner_customer_note.html', {
        'form': form, 'business': business, 'customer': customer
    })


@login_required
def owner_analytics(request):
    business, err = _require_owner(request.user)
    if err:
        return err
    if not business:
        return redirect('core:owner_register_business')

    today = timezone.localtime(timezone.now()).date()
    thirty_days_ago = today - timedelta(days=29)

    # Bookings per day (last 30 days)
    bookings_qs = Booking.objects.filter(
        service__business=business,
        date__gte=thirty_days_ago,
        date__lte=today,
        status__in=(Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED, Booking.STATUS_PENDING),
    )

    days_range = [(thirty_days_ago + timedelta(days=i)) for i in range(30)]
    bookings_by_date = defaultdict(int)
    for b in bookings_qs:
        bookings_by_date[b.date] += 1

    daily_labels = [d.strftime('%d %b') for d in days_range]
    daily_data = [bookings_by_date.get(d, 0) for d in days_range]

    # Revenue per week (last 8 weeks)
    eight_weeks_ago = today - timedelta(weeks=8)
    paid_bookings = Booking.objects.filter(
        service__business=business,
        status__in=(Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED),
        date__gte=eight_weeks_ago,
    )

    week_revenue = defaultdict(float)
    for b in paid_bookings:
        week_num = (b.date - eight_weeks_ago).days // 7
        week_revenue[week_num] += float(b.service.price)

    week_labels = [f"Week {i+1}" for i in range(8)]
    week_data = [round(week_revenue.get(i, 0), 2) for i in range(8)]

    # Busiest hours
    hour_counts = defaultdict(int)
    all_bookings = Booking.objects.filter(
        service__business=business,
        status__in=(Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED),
    )
    for b in all_bookings:
        hour_counts[b.start_time.hour] += 1

    hour_labels = [f"{h:02d}:00" for h in range(6, 22)]
    hour_data = [hour_counts.get(h, 0) for h in range(6, 22)]

    # Stats
    total_bookings = Booking.objects.filter(service__business=business).count()
    completed_bookings = Booking.objects.filter(
        service__business=business, status=Booking.STATUS_COMPLETED
    ).count()
    no_shows = Booking.objects.filter(
        service__business=business, status=Booking.STATUS_NO_SHOW
    ).count()
    no_show_rate = round((no_shows / total_bookings * 100) if total_bookings else 0, 1)

    total_revenue = Booking.objects.filter(
        service__business=business,
        status__in=(Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED),
    ).aggregate(total=Sum('service__price'))['total'] or 0

    # Most popular service
    popular_service = Service.objects.filter(business=business).annotate(
        booking_count=Count('bookings', filter=Q(
            bookings__status__in=(Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED)
        ))
    ).order_by('-booking_count').first()

    # Busy-time insight (simulated AI)
    busy_insight = _compute_busy_insight(business)

    context = {
        'business': business,
        'daily_labels': json.dumps(daily_labels),
        'daily_data': json.dumps(daily_data),
        'week_labels': json.dumps(week_labels),
        'week_data': json.dumps(week_data),
        'hour_labels': json.dumps(hour_labels),
        'hour_data': json.dumps(hour_data),
        'total_bookings': total_bookings,
        'completed_bookings': completed_bookings,
        'no_show_rate': no_show_rate,
        'total_revenue': total_revenue,
        'popular_service': popular_service,
        'busy_insight': busy_insight,
    }
    return render(request, 'core/owner_analytics.html', context)


def _compute_busy_insight(business):
    """Simulated AI busy-time insight (rule-based)."""
    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    bookings = Booking.objects.filter(
        service__business=business,
        status__in=(Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED),
    )
    if not bookings.exists():
        return "Not enough booking history yet. Insight will appear after more bookings."

    # Count by (day_of_week, hour)
    slot_counts = defaultdict(int)
    for b in bookings:
        key = (b.date.weekday(), b.start_time.hour)
        slot_counts[key] += 1

    if not slot_counts:
        return "Not enough data for insight."

    busiest = max(slot_counts, key=slot_counts.get)
    busiest_day = DAY_NAMES[busiest[0]]
    busiest_hour = f"{busiest[1]:02d}:00"

    # Find quietest day
    day_counts = defaultdict(int)
    for (day, hour), count in slot_counts.items():
        day_counts[day] += count

    quietest_day_idx = min(range(7), key=lambda d: day_counts.get(d, 0))
    quietest_day = DAY_NAMES[quietest_day_idx]

    return (
        f"{busiest_day}s around {busiest_hour} are your busiest time — "
        f"consider a discount on {quietest_day} mornings to increase bookings then."
    )


@login_required
def owner_register_business(request):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return redirect('core:home')
    if not profile.is_owner:
        messages.error(request, "Only business owners can register businesses.")
        return redirect('core:home')

    # If already has a business, redirect to dashboard
    existing = Business.objects.filter(owner=request.user).first()
    if existing:
        return redirect('core:owner_dashboard')

    form = BusinessProfileForm()
    if request.method == 'POST':
        form = BusinessProfileForm(request.POST)
        if form.is_valid():
            business = form.save(commit=False)
            business.owner = request.user
            business.save()
            # Create default hours (Mon-Fri 8am-6pm, Sat 9am-4pm, Sun closed)
            from datetime import time as t
            default_hours = [
                (0, t(8, 0), t(18, 0), False),
                (1, t(8, 0), t(18, 0), False),
                (2, t(8, 0), t(18, 0), False),
                (3, t(8, 0), t(18, 0), False),
                (4, t(8, 0), t(18, 0), False),
                (5, t(9, 0), t(16, 0), False),
                (6, None, None, True),
            ]
            for day, o, c, closed in default_hours:
                BusinessHours.objects.create(
                    business=business, day_of_week=day,
                    open_time=o, close_time=c, is_closed=closed,
                )
            messages.success(request, f"Business '{business.name}' registered! Now add your services.")
            return redirect('core:owner_services')

    return render(request, 'core/owner_register_business.html', {'form': form})


# ---------------------------------------------------------------------------
# Platform admin
# ---------------------------------------------------------------------------

@login_required
def platform_totals(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff access required.")

    total_businesses = Business.objects.count()
    total_bookings = Booking.objects.count()
    total_revenue = Payment.objects.filter(
        status__in=Payment.PAID_STATUSES
    ).aggregate(total=Sum('amount'))['total'] or 0
    verified_businesses = Business.objects.filter(is_verified=True).count()

    # Bookings per day (last 30 days)
    today = timezone.localtime(timezone.now()).date()
    thirty_days_ago = today - timedelta(days=29)
    days_range = [(thirty_days_ago + timedelta(days=i)) for i in range(30)]
    bookings_qs = Booking.objects.filter(date__gte=thirty_days_ago, date__lte=today)
    bookings_by_date = defaultdict(int)
    for b in bookings_qs:
        bookings_by_date[b.date] += 1

    daily_labels = json.dumps([d.strftime('%d %b') for d in days_range])
    daily_data = json.dumps([bookings_by_date.get(d, 0) for d in days_range])

    context = {
        'total_businesses': total_businesses,
        'total_bookings': total_bookings,
        'total_revenue': total_revenue,
        'verified_businesses': verified_businesses,
        'daily_labels': daily_labels,
        'daily_data': daily_data,
    }
    return render(request, 'core/platform_totals.html', context)
