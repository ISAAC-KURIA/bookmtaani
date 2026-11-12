"""
Booking logic service functions.
All booking validation and creation goes here.
"""


def get_user_role(user):
    """
    Return the role string for a user.
    Values: 'anonymous', 'admin', 'owner', 'customer'
    'admin' means Django staff (is_staff=True).
    'owner' and 'customer' come from UserProfile.role.
    """
    if not user or not user.is_authenticated:
        return 'anonymous'
    if user.is_staff:
        return 'admin'
    try:
        profile = user.profile
        return profile.role  # 'owner' or 'customer'
    except Exception:
        return 'customer'
from datetime import datetime, timedelta, date as date_type
from django.db import transaction
from django.utils import timezone
from django.utils.timezone import make_aware
from django.core.exceptions import ValidationError


def get_available_slots(service, booking_date):
    """
    Returns list of available time slot strings (HH:MM) for a service on a given date.
    Respects:
    - Business hours for that day
    - Existing confirmed/pending bookings
    - TimeBlocks (lunch, closed, etc.)
    - No slots in the past
    - No slots outside opening hours
    """
    from .models import Booking, TimeBlock, BusinessHours

    business = service.business
    duration = timedelta(minutes=service.duration_minutes)

    # Get business hours for this day (0=Mon, 6=Sun)
    day_of_week = booking_date.weekday()
    try:
        bh = BusinessHours.objects.get(business=business, day_of_week=day_of_week)
    except BusinessHours.DoesNotExist:
        return []

    if bh.is_closed or bh.open_time is None or bh.close_time is None:
        return []

    # Build list of slots from open to close, step = service duration
    open_dt = datetime.combine(booking_date, bh.open_time)
    close_dt = datetime.combine(booking_date, bh.close_time)

    # Get existing bookings for this business on this date (active)
    existing_bookings = Booking.objects.filter(
        service__business=business,
        date=booking_date,
        status__in=(Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED),
    ).values_list('start_time', 'end_time')

    # Get time blocks for this date
    time_blocks = TimeBlock.objects.filter(
        business=business,
        date=booking_date,
    ).values_list('start_time', 'end_time')

    # Current time for "no past bookings" check
    now = timezone.localtime(timezone.now())
    today = now.date()

    slots = []
    slot_start = open_dt
    while slot_start + duration <= close_dt:
        slot_end = slot_start + duration

        # Skip past slots if booking today
        if booking_date == today:
            slot_aware = make_aware(slot_start)
            if slot_aware <= now:
                slot_start += duration
                continue

        # Check overlap with existing bookings
        overlaps = False
        for b_start, b_end in existing_bookings:
            b_start_dt = datetime.combine(booking_date, b_start)
            b_end_dt = datetime.combine(booking_date, b_end)
            if slot_start < b_end_dt and slot_end > b_start_dt:
                overlaps = True
                break

        if not overlaps:
            # Check overlap with time blocks
            for tb_start, tb_end in time_blocks:
                tb_start_dt = datetime.combine(booking_date, tb_start)
                tb_end_dt = datetime.combine(booking_date, tb_end)
                if slot_start < tb_end_dt and slot_end > tb_start_dt:
                    overlaps = True
                    break

        if not overlaps:
            slots.append(slot_start.strftime('%H:%M'))

        slot_start += duration

    return slots


@transaction.atomic
def create_booking(customer, service, booking_date, start_time_str):
    """
    Creates a booking with double-booking prevention.
    Uses select_for_update() to lock rows and prevent race conditions.
    Raises ValidationError on conflict.
    """
    from .models import Booking, BusinessHours, TimeBlock

    business = service.business
    duration = timedelta(minutes=service.duration_minutes)

    # Parse start time
    if isinstance(start_time_str, str):
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
    else:
        start_time = start_time_str

    start_dt = datetime.combine(booking_date, start_time)
    end_dt = start_dt + duration
    end_time = end_dt.time()

    # Validate not in the past
    now = timezone.localtime(timezone.now())
    start_aware = make_aware(start_dt)
    if start_aware <= now:
        raise ValidationError("Cannot book a slot in the past.")

    # Validate business hours
    day_of_week = booking_date.weekday()
    try:
        bh = BusinessHours.objects.get(business=business, day_of_week=day_of_week)
    except BusinessHours.DoesNotExist:
        raise ValidationError("Business has no hours set for this day.")

    if bh.is_closed:
        raise ValidationError("Business is closed on this day.")

    if bh.open_time is None or bh.close_time is None:
        raise ValidationError("Business hours not set for this day.")

    if start_time < bh.open_time or end_time > bh.close_time:
        raise ValidationError("Slot is outside business opening hours.")

    # Lock existing bookings for this business/date to prevent race condition
    existing = Booking.objects.select_for_update().filter(
        service__business=business,
        date=booking_date,
        status__in=(Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED),
    )

    for b in existing:
        b_start_dt = datetime.combine(booking_date, b.start_time)
        b_end_dt = datetime.combine(booking_date, b.end_time)
        if start_dt < b_end_dt and end_dt > b_start_dt:
            raise ValidationError("This time slot is no longer available. Please choose another.")

    # Check time blocks
    blocks = TimeBlock.objects.select_for_update().filter(
        business=business,
        date=booking_date,
    )
    for tb in blocks:
        tb_start_dt = datetime.combine(booking_date, tb.start_time)
        tb_end_dt = datetime.combine(booking_date, tb.end_time)
        if start_dt < tb_end_dt and end_dt > tb_start_dt:
            raise ValidationError("Business is blocked during this time.")

    booking = Booking.objects.create(
        customer=customer,
        service=service,
        date=booking_date,
        start_time=start_time,
        end_time=end_time,
        status=Booking.STATUS_PENDING,
    )
    return booking


def create_sms_notifications(booking):
    """Create simulated SMS notifications for 24h and 1h before booking."""
    from .models import SMSNotification
    from django.utils.timezone import make_aware
    from datetime import datetime, timedelta

    booking_dt = datetime.combine(booking.date, booking.start_time)
    try:
        booking_dt = make_aware(booking_dt)
    except Exception:
        pass

    business = booking.service.business
    customer_name = booking.customer.get_full_name() or booking.customer.username
    service_name = booking.service.name
    time_str = booking.start_time.strftime('%I:%M %p')
    date_str = booking.date.strftime('%d %b %Y')

    for hours_before, label in [(24, '24-hour'), (1, '1-hour')]:
        scheduled = booking_dt - timedelta(hours=hours_before)
        content = (
            f"Hi {customer_name}, reminder: your {service_name} "
            f"appointment at {business.name} is on {date_str} at {time_str}. "
            f"This is your {label} reminder. — BookMtaani"
        )
        SMSNotification.objects.create(
            booking=booking,
            scheduled_at=scheduled,
            content=content,
            status='simulated',
        )


# ===========================================================================
# "Best time to book" — busy-level suggestion
#
# Labels each available slot Quiet / Normal / Busy (or "Not enough data")
# from the business's past bookings in the database. This is a transparent
# rule-based heuristic, NOT a machine-learning model.
#
# Which bookings count as historical "real" demand:
#   Only CONFIRMED and COMPLETED bookings are counted. These are bookings
#   that actually occupied the slot (honored demand). PENDING may still be
#   cancelled, CANCELLED freed the slot, and NO_SHOW means the customer never
#   arrived so the business experienced that slot as quiet — counting any of
#   those as "busy" would mislead.
#
# Not-enough-data threshold:
#   If the business has fewer than BUSY_MIN_HISTORY (= 5) total real
#   historical bookings, every slot is labeled "Not enough data" rather than
#   guessing. A single global threshold keeps the rule simple and testable.
#
# Level thresholds (relative to the business's own average):
#   Group real bookings by (weekday, hour). mean = total real bookings divided
#   by the number of distinct occupied (weekday, hour) buckets. For a slot,
#   ratio = count(its weekday, hour) / mean.
#       ratio >= 1.3 -> Busy
#       ratio <= 0.7 -> Quiet
#       otherwise   -> Normal
#   A slot with no past bookings has count 0 -> ratio 0 -> Quiet, which is
#   reasonable once the business has enough history overall.
# ===========================================================================

BUSY_MIN_HISTORY = 5
BUSY_BUSY_RATIO = 1.3
BUSY_QUIET_RATIO = 0.7

LEVEL_QUIET = 'quiet'
LEVEL_NORMAL = 'normal'
LEVEL_BUSY = 'busy'
LEVEL_NO_DATA = 'no_data'

# level -> (label, Font Awesome icon class, message shown for a selected slot)
_LEVEL_META = {
    LEVEL_QUIET: (
        'Quiet',
        'fa-circle-check',
        'Usually quiet at this time, good choice',
    ),
    LEVEL_NORMAL: (
        'Normal',
        'fa-clock',
        'A usual number of bookings at this time',
    ),
    LEVEL_BUSY: (
        'Busy',
        'fa-triangle-exclamation',
        'Usually busy at this time, you may wait',
    ),
    LEVEL_NO_DATA: (
        'Not enough data',
        'fa-circle-question',
        'Not enough booking history to estimate this slot yet',
    ),
}

BUSY_BASIS_LABEL = 'Simulated insight (rule-based, from booking history)'


def _booking_counts(business):
    """
    Count the business's real historical bookings grouped by (weekday, hour).

    Returns a tuple (counts, total_real, num_buckets) where ``counts`` maps
    (weekday, hour) -> int, ``total_real`` is the count of CONFIRMED+COMPLETED
    bookings, and ``num_buckets`` is the number of distinct (weekday, hour)
    keys with at least one booking.
    """
    from .models import Booking

    counts = {}
    total = 0
    qs = Booking.objects.filter(
        service__business=business,
        status__in=(Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED),
    ).values_list('date', 'start_time')
    for booking_date, start_time in qs:
        key = (booking_date.weekday(), start_time.hour)
        counts[key] = counts.get(key, 0) + 1
        total += 1
    return counts, total, len(counts)


def _classify_ratio(ratio):
    """Map a count/mean ratio to a busy level string."""
    if ratio >= BUSY_BUSY_RATIO:
        return LEVEL_BUSY
    if ratio <= BUSY_QUIET_RATIO:
        return LEVEL_QUIET
    return LEVEL_NORMAL


def _slot_info(slot, level, suggestions=None):
    """Build the per-slot info dict the template renders."""
    label, icon, message = _LEVEL_META[level]
    return {
        'time': slot,
        'level': level,
        'level_label': label,
        'icon': icon,
        'message': message,
        'suggestions': suggestions or [],
    }


def get_slot_busy_levels(business, selected_date, slots):
    """
    Compute a busy level for each available slot for ``selected_date``.

    ``slots`` is a list of 'HH:MM' strings (the output of get_available_slots).
    ``selected_date`` is the date the customer is booking for; its weekday is
    used to pick the matching historical counts.

    Returns a dict::

        {
          'slots': [info, ...],   # one info per slot, same order as `slots`
          'has_data': bool,       # total real bookings >= BUSY_MIN_HISTORY
          'basis': str,           # human-facing heuristic label
        }

    where each ``info`` is the dict produced by ``_slot_info``. The template
    never computes busy levels itself; it only displays these precomputed
    values.
    """
    counts, total_real, num_buckets = _booking_counts(business)

    # Too little history: don't guess.
    if total_real < BUSY_MIN_HISTORY:
        return {
            'slots': [_slot_info(s, LEVEL_NO_DATA) for s in slots],
            'has_data': False,
            'basis': BUSY_BASIS_LABEL,
        }

    mean = total_real / num_buckets if num_buckets else 0.0
    target_weekday = selected_date.weekday()

    # First pass: classify each slot's level from its (weekday, hour) history.
    levels = []
    for slot in slots:
        hour = int(slot.split(':')[0])
        count = counts.get((target_weekday, hour), 0)
        ratio = count / mean if mean else 0.0
        levels.append(_classify_ratio(ratio))

    # Second pass: for Busy slots, suggest up to two nearest (by list index)
    # slots that are Quiet or Normal, so the customer has a calmer alternative.
    infos = []
    for i, slot in enumerate(slots):
        level = levels[i]
        suggestions = []
        if level == LEVEL_BUSY:
            candidates = sorted(
                ((abs(i - j), j) for j, lvl in enumerate(levels)
                 if lvl in (LEVEL_QUIET, LEVEL_NORMAL)),
                key=lambda x: (x[0], x[1]),
            )
            for _, j in candidates[:2]:
                suggestions.append(slots[j])
        infos.append(_slot_info(slot, level, suggestions))

    return {
        'slots': infos,
        'has_data': True,
        'basis': BUSY_BASIS_LABEL,
    }
