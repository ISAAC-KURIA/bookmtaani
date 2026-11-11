"""
Booking logic service functions.
All booking validation and creation goes here.
"""
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
            f"[SIMULATED SMS] Hi {customer_name}, reminder: your {service_name} "
            f"appointment at {business.name} is on {date_str} at {time_str}. "
            f"This is your {label} reminder. — BookMtaani"
        )
        SMSNotification.objects.create(
            booking=booking,
            scheduled_at=scheduled,
            content=content,
            status='simulated',
        )
