"""
Tests for the "Best time to book" busy-level service function:
- Quiet slot (historical count well below the business average)
- Normal slot (count near the average)
- Busy slot (count well above the average) plus quieter nearby suggestions
- Not enough data (fewer than BUSY_MIN_HISTORY total real bookings)

The fixture below is hand-checked:
    Monday 09:00 = 6 bookings
    Monday 10:00 = 3 bookings
    Monday 11:00 = 1 booking
    Tuesday 09:00 = 3 bookings
    Tuesday 10:00 = 3 bookings
    total real = 16, distinct occupied buckets = 5, mean = 16/5 = 3.2
    Monday 09:00 ratio = 6/3.2 = 1.875  -> Busy   (>= 1.3)
    Monday 10:00 ratio = 3/3.2 = 0.9375 -> Normal (between 0.7 and 1.3)
    Monday 11:00 ratio = 1/3.2 = 0.3125 -> Quiet  (<= 0.7)
"""
from datetime import date, time, timedelta

from django.test import TestCase
from django.contrib.auth.models import User

from core.models import UserProfile, Business, Service, Booking
from core.services import get_slot_busy_levels


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
    return Business.objects.create(
        owner=owner, name='Busy Test Business', category='kinyozi', town='Kisii',
    )


def _make_service(business, duration=30):
    return Service.objects.create(
        business=business, name='Haircut', price=300, duration_minutes=duration,
    )


def _next_weekday(weekday):
    """Return the next date that falls on `weekday` (0=Mon, 6=Sun), always in the future."""
    today = date.today()
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _past_dates_for_weekday(weekday, n):
    """Return n distinct past dates that fall on `weekday` (0=Mon..6=Sun), most recent first."""
    today = date.today()
    days_back = (today.weekday() - weekday) % 7
    if days_back == 0:
        days_back = 7
    base = today - timedelta(days=days_back)
    return [base - timedelta(weeks=i) for i in range(n)]


class BusyLevelTest(TestCase):
    def setUp(self):
        self.owner = _make_user('bt_owner', 'owner')
        self.business = _make_business(self.owner)
        self.service = _make_service(self.business, duration=30)
        self.customer = _make_user('bt_customer')
        # A future Monday for slot selection.
        self.monday = _next_weekday(0)

    def _add_bookings(self, weekday, hour, count, status=Booking.STATUS_CONFIRMED):
        """Create `count` real historical bookings on distinct past dates of `weekday` at `hour`."""
        for d in _past_dates_for_weekday(weekday, count):
            Booking.objects.create(
                customer=self.customer,
                service=self.service,
                date=d,
                start_time=time(hour, 0),
                end_time=time(hour, 30),
                status=status,
            )

    def _build_levels_fixture(self):
        # Monday (0): 09:00 x6, 10:00 x3, 11:00 x1
        self._add_bookings(0, 9, 6)
        self._add_bookings(0, 10, 3)
        self._add_bookings(0, 11, 1)
        # Tuesday (1): 09:00 x3, 10:00 x3
        self._add_bookings(1, 9, 3)
        self._add_bookings(1, 10, 3)

    def test_quiet_slot(self):
        """A slot whose historical count is well below the mean is Quiet."""
        self._build_levels_fixture()
        result = get_slot_busy_levels(self.business, self.monday, ['09:00', '10:00', '11:00'])
        info = result['slots'][2]  # 11:00 -> ratio 0.3125
        self.assertEqual(info['level'], 'quiet')
        self.assertEqual(info['level_label'], 'Quiet')
        self.assertEqual(info['icon'], 'fa-circle-check')
        self.assertIn('quiet', info['message'].lower())
        # Quiet slots do not carry suggestions.
        self.assertEqual(info['suggestions'], [])

    def test_normal_slot(self):
        """A slot whose historical count is near the mean is Normal."""
        self._build_levels_fixture()
        result = get_slot_busy_levels(self.business, self.monday, ['09:00', '10:00', '11:00'])
        info = result['slots'][1]  # 10:00 -> ratio 0.9375
        self.assertEqual(info['level'], 'normal')
        self.assertEqual(info['level_label'], 'Normal')
        self.assertEqual(info['icon'], 'fa-clock')

    def test_busy_slot(self):
        """A slot well above the mean is Busy and suggests quieter nearby slots."""
        self._build_levels_fixture()
        result = get_slot_busy_levels(self.business, self.monday, ['09:00', '10:00', '11:00'])
        self.assertTrue(result['has_data'])
        info = result['slots'][0]  # 09:00 -> ratio 1.875
        self.assertEqual(info['level'], 'busy')
        self.assertEqual(info['level_label'], 'Busy')
        self.assertEqual(info['icon'], 'fa-triangle-exclamation')
        self.assertIn('busy', info['message'].lower())
        # One to two quieter nearby slots (the Normal 10:00 and Quiet 11:00).
        self.assertGreaterEqual(len(info['suggestions']), 1)
        self.assertLessEqual(len(info['suggestions']), 2)
        slot_times = ['09:00', '10:00', '11:00']
        for s in info['suggestions']:
            self.assertIn(s, slot_times)
            self.assertNotEqual(s, '09:00')  # never suggest the busy slot itself

    def test_not_enough_data(self):
        """With fewer than 5 total real bookings, every slot is 'Not enough data'."""
        # Only 4 total real bookings (< BUSY_MIN_HISTORY = 5).
        self._add_bookings(0, 9, 4)
        result = get_slot_busy_levels(self.business, self.monday, ['09:00', '10:00', '11:00'])
        self.assertFalse(result['has_data'])
        self.assertEqual(len(result['slots']), 3)
        for info in result['slots']:
            self.assertEqual(info['level'], 'no_data')
            self.assertEqual(info['level_label'], 'Not enough data')
            self.assertEqual(info['icon'], 'fa-circle-question')
            self.assertIn('not enough', info['message'].lower())
            self.assertEqual(info['suggestions'], [])

    def test_basis_label_present(self):
        """The heuristic label is always returned so the UI can show it."""
        self._build_levels_fixture()
        result = get_slot_busy_levels(self.business, self.monday, ['09:00', '10:00', '11:00'])
        self.assertEqual(
            result['basis'],
            'Simulated insight (rule-based, from booking history)',
        )

    def test_cancelled_and_pending_not_counted(self):
        """Cancelled, pending and no-show bookings are not treated as real demand."""
        self._add_bookings(0, 9, 6, status=Booking.STATUS_CONFIRMED)
        # These should NOT change the counts/levels.
        self._add_bookings(0, 9, 5, status=Booking.STATUS_CANCELLED)
        self._add_bookings(0, 9, 5, status=Booking.STATUS_PENDING)
        self._add_bookings(0, 9, 5, status=Booking.STATUS_NO_SHOW)
        result = get_slot_busy_levels(self.business, self.monday, ['09:00'])
        self.assertTrue(result['has_data'])  # 6 real bookings >= 5
        info = result['slots'][0]
        # Only the 6 confirmed bookings count; one bucket -> mean 6 -> ratio 1.0 -> Normal.
        self.assertEqual(info['level'], 'normal')
