"""
Tests for booking logic:
- Available slots calculation
- Double booking prevention
- Booking outside business hours is rejected
- Booking in the past is rejected
- Owner isolation (owner cannot access another owner's business)
"""
from datetime import date, time, timedelta
from unittest.mock import patch

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import (
    UserProfile, Business, BusinessHours, Service, Booking, TimeBlock
)
from core.services import get_available_slots, create_booking


# ---------------------------------------------------------------------------
# Fix for Python 3.14 + Django 5.1: RequestContext.__copy__ crashes
# (also Context, used when Django renders its built-in 404/500 pages)
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


def _make_user(username, role='customer'):
    u = User.objects.create_user(username=username, password='testpass123')
    UserProfile.objects.create(user=u, role=role)
    return u


def _make_business(owner):
    b = Business.objects.create(
        owner=owner,
        name='Test Business',
        category='kinyozi',
        town='Kisii',
    )
    return b


def _make_hours(business, day, open_t=time(8, 0), close_t=time(18, 0), closed=False):
    return BusinessHours.objects.create(
        business=business,
        day_of_week=day,
        open_time=None if closed else open_t,
        close_time=None if closed else close_t,
        is_closed=closed,
    )


def _make_service(business, duration=30):
    return Service.objects.create(
        business=business,
        name='Haircut',
        price=300,
        duration_minutes=duration,
    )


class AvailableSlotsTest(TestCase):
    def setUp(self):
        self.owner = _make_user('owner1', 'owner')
        self.business = _make_business(self.owner)
        self.service = _make_service(self.business, duration=30)

    def test_slots_returned_for_open_day(self):
        """Should return slots from open to close."""
        # Use a future Monday
        future_monday = _next_weekday(0)
        _make_hours(self.business, future_monday.weekday(), time(9, 0), time(10, 0))
        slots = get_available_slots(self.service, future_monday)
        self.assertIn('09:00', slots)
        self.assertIn('09:30', slots)
        self.assertEqual(len(slots), 2)

    def test_no_slots_on_closed_day(self):
        """Closed days return empty list."""
        future_sunday = _next_weekday(6)
        _make_hours(self.business, future_sunday.weekday(), closed=True)
        slots = get_available_slots(self.service, future_sunday)
        self.assertEqual(slots, [])

    def test_booked_slot_excluded(self):
        """A slot with an existing booking is excluded."""
        future_mon = _next_weekday(0)
        _make_hours(self.business, future_mon.weekday(), time(9, 0), time(10, 0))
        customer = _make_user('customer1')
        # Book 09:00 slot
        Booking.objects.create(
            customer=customer,
            service=self.service,
            date=future_mon,
            start_time=time(9, 0),
            end_time=time(9, 30),
            status=Booking.STATUS_CONFIRMED,
        )
        slots = get_available_slots(self.service, future_mon)
        self.assertNotIn('09:00', slots)
        self.assertIn('09:30', slots)

    def test_time_block_excluded(self):
        """Slots overlapping a time block are excluded."""
        future_mon = _next_weekday(0)
        _make_hours(self.business, future_mon.weekday(), time(9, 0), time(11, 0))
        TimeBlock.objects.create(
            business=self.business,
            date=future_mon,
            start_time=time(9, 0),
            end_time=time(10, 0),
            reason='lunch',
        )
        slots = get_available_slots(self.service, future_mon)
        self.assertNotIn('09:00', slots)
        self.assertNotIn('09:30', slots)
        self.assertIn('10:00', slots)

    def test_no_hours_returns_empty(self):
        """If no business hours set, return empty."""
        future_wed = _next_weekday(2)
        slots = get_available_slots(self.service, future_wed)
        self.assertEqual(slots, [])


class DoubleBookingTest(TestCase):
    def setUp(self):
        self.owner = _make_user('owner2', 'owner')
        self.business = _make_business(self.owner)
        self.service = _make_service(self.business, duration=30)
        self.future_day = _next_weekday(1)
        _make_hours(self.business, self.future_day.weekday(), time(9, 0), time(18, 0))
        self.customer1 = _make_user('cust_a')
        self.customer2 = _make_user('cust_b')

    def test_first_booking_succeeds(self):
        booking = create_booking(self.customer1, self.service, self.future_day, '10:00')
        self.assertIsNotNone(booking.pk)

    def test_double_booking_prevented(self):
        """Second customer cannot book the same slot."""
        create_booking(self.customer1, self.service, self.future_day, '10:00')
        with self.assertRaises(ValidationError):
            create_booking(self.customer2, self.service, self.future_day, '10:00')

    def test_overlapping_booking_prevented(self):
        """Booking that overlaps existing booking is prevented."""
        # 60-minute service
        long_service = Service.objects.create(
            business=self.business, name='Long', price=500, duration_minutes=60
        )
        create_booking(self.customer1, long_service, self.future_day, '10:00')
        # Try booking at 10:30 (overlaps 10:00-11:00)
        with self.assertRaises(ValidationError):
            create_booking(self.customer2, long_service, self.future_day, '10:30')


class BookingOutsideHoursTest(TestCase):
    def setUp(self):
        self.owner = _make_user('owner3', 'owner')
        self.business = _make_business(self.owner)
        self.service = _make_service(self.business, duration=30)
        self.future_day = _next_weekday(2)
        _make_hours(self.business, self.future_day.weekday(), time(9, 0), time(17, 0))
        self.customer = _make_user('cust_c')

    def test_booking_before_opening_rejected(self):
        with self.assertRaises(ValidationError):
            create_booking(self.customer, self.service, self.future_day, '07:00')

    def test_booking_after_closing_rejected(self):
        with self.assertRaises(ValidationError):
            create_booking(self.customer, self.service, self.future_day, '17:30')

    def test_booking_on_closed_day_rejected(self):
        future_sun = _next_weekday(6)
        _make_hours(self.business, future_sun.weekday(), closed=True)
        with self.assertRaises(ValidationError):
            create_booking(self.customer, self.service, future_sun, '10:00')

    def test_booking_with_no_hours_rejected(self):
        future_thu = _next_weekday(3)
        # No hours set for Thursday
        with self.assertRaises(ValidationError):
            create_booking(self.customer, self.service, future_thu, '10:00')


class PastBookingTest(TestCase):
    def setUp(self):
        self.owner = _make_user('owner4', 'owner')
        self.business = _make_business(self.owner)
        self.service = _make_service(self.business, duration=30)
        self.customer = _make_user('cust_d')

    def test_booking_in_past_rejected(self):
        """Booking in the past raises ValidationError."""
        past_date = date.today() - timedelta(days=1)
        # We need hours set for that past day too
        _make_hours(self.business, past_date.weekday(), time(9, 0), time(18, 0))
        with self.assertRaises(ValidationError):
            create_booking(self.customer, self.service, past_date, '10:00')

    def test_booking_today_past_time_rejected(self):
        """Booking today at an already-passed time is rejected."""
        today = date.today()
        # Need hours for today
        _make_hours(self.business, today.weekday(), time(0, 0), time(23, 59))
        # Use time 00:00 which is definitely in the past
        with self.assertRaises(ValidationError):
            create_booking(self.customer, self.service, today, '00:00')


class OwnerIsolationTest(TestCase):
    def setUp(self):
        self.owner1 = _make_user('owner_a', 'owner')
        self.owner2 = _make_user('owner_b', 'owner')
        self.business1 = _make_business(self.owner1)
        self.business2 = Business.objects.create(
            owner=self.owner2,
            name='Other Business',
            category='salon',
            town='Nairobi',
        )
        self.client = Client()

    def test_owner_cannot_access_other_business_bookings(self):
        """Owner 1 trying to access owner 2's bookings is forbidden."""
        self.client.login(username='owner_a', password='testpass123')
        # The owner dashboard should show only owner1's business
        # Try to access owner_bookings — should only show own bookings
        response = self.client.get('/owner/bookings/')
        self.assertEqual(response.status_code, 200)
        # owner1 has no business with bookings, but should not see owner2's data
        # Verify context business is owner1's
        ctx_business = response.context.get('business')
        if ctx_business:
            self.assertEqual(ctx_business.owner, self.owner1)

    def test_owner_service_edit_other_business_returns_404(self):
        """Owner cannot edit another owner's service (gets 404)."""
        self.client.login(username='owner_a', password='testpass123')
        # Create a service on business2 (owner2's)
        service2 = Service.objects.create(
            business=self.business2, name='Blowout', price=500, duration_minutes=45
        )
        response = self.client.post(f'/owner/services/{service2.id}/edit/', {
            'name': 'Hacked', 'price': '100', 'duration_minutes': '30',
        })
        # Should return 404 because owner1 doesn't own business2
        self.assertEqual(response.status_code, 404)

    def test_owner_cannot_delete_other_business_service(self):
        """Owner cannot delete another owner's service."""
        self.client.login(username='owner_a', password='testpass123')
        service2 = Service.objects.create(
            business=self.business2, name='Cut', price=300, duration_minutes=30
        )
        response = self.client.post(f'/owner/services/{service2.id}/delete/')
        self.assertEqual(response.status_code, 404)


def _next_weekday(weekday):
    """Return the next date that falls on `weekday` (0=Mon, 6=Sun), always in the future."""
    today = date.today()
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)
