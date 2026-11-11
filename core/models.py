from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
import uuid


class UserProfile(models.Model):
    ROLE_CUSTOMER = 'customer'
    ROLE_OWNER = 'owner'
    ROLE_CHOICES = [
        (ROLE_CUSTOMER, 'Customer'),
        (ROLE_OWNER, 'Business Owner'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CUSTOMER)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_owner(self):
        return self.role == self.ROLE_OWNER

    @property
    def is_customer(self):
        return self.role == self.ROLE_CUSTOMER


class Business(models.Model):
    CATEGORY_CHOICES = [
        ('kinyozi', 'Kinyozi (Barber)'),
        ('salon', 'Salon'),
        ('laundry', 'Laundry'),
        ('car_wash', 'Car Wash'),
        ('spa', 'Spa'),
        ('nail_tech', 'Nail Technician'),
        ('fitness', 'Fitness Trainer'),
    ]
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='businesses')
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    town = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Businesses'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            n = 1
            while Business.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def average_rating(self):
        reviews = Review.objects.filter(booking__service__business=self)
        if reviews.exists():
            return round(reviews.aggregate(models.Avg('rating'))['rating__avg'], 1)
        return None

    def review_count(self):
        return Review.objects.filter(booking__service__business=self).count()

    def get_category_icon(self):
        icons = {
            'kinyozi': 'fa-scissors',
            'salon': 'fa-spa',
            'laundry': 'fa-tshirt',
            'car_wash': 'fa-car',
            'spa': 'fa-hot-tub-person',
            'nail_tech': 'fa-hand-sparkles',
            'fitness': 'fa-dumbbell',
        }
        return icons.get(self.category, 'fa-store')


class BusinessHours(models.Model):
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='hours')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    open_time = models.TimeField(null=True, blank=True)
    close_time = models.TimeField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('business', 'day_of_week')
        ordering = ['day_of_week']

    def __str__(self):
        day = dict(self.DAY_CHOICES).get(self.day_of_week, '')
        if self.is_closed:
            return f"{self.business.name} - {day}: Closed"
        return f"{self.business.name} - {day}: {self.open_time} - {self.close_time}"


class Service(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_minutes = models.PositiveIntegerField(default=30)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.business.name} - {self.name} (KES {self.price})"


class TimeBlock(models.Model):
    REASON_CHOICES = [
        ('lunch', 'Lunch Break'),
        ('closed', 'Closed'),
        ('other', 'Other'),
    ]
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='time_blocks')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default='other')
    notes = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.business.name} - {self.date} {self.start_time}-{self.end_time} ({self.reason})"


class Booking(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_NO_SHOW = 'no_show'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_NO_SHOW, 'No Show'),
    ]
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='bookings')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['date', 'start_time']

    def __str__(self):
        return f"{self.customer.username} - {self.service.name} on {self.date} at {self.start_time}"

    def can_cancel(self):
        from datetime import datetime, date
        if self.status in (self.STATUS_CANCELLED, self.STATUS_COMPLETED, self.STATUS_NO_SHOW):
            return False
        now = timezone.localtime(timezone.now())
        booking_dt = datetime.combine(self.date, self.start_time)
        from django.utils.timezone import make_aware
        try:
            booking_dt = make_aware(booking_dt)
        except Exception:
            pass
        return booking_dt > now

    def can_review(self):
        return self.status == self.STATUS_COMPLETED and not hasattr(self, 'review')

    @property
    def total_price(self):
        return self.service.price


class Payment(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'simulated_success'
    STATUS_FAILED = 'simulated_failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Simulated Success'),
        (STATUS_FAILED, 'Simulated Failed'),
    ]
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=30, default='mpesa_simulated')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING)
    transaction_ref = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    phone_number = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"Payment for {self.booking} - {self.status}"


class SMSNotification(models.Model):
    STATUS_SIMULATED = 'simulated'
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='sms_notifications')
    scheduled_at = models.DateTimeField()
    content = models.TextField()
    status = models.CharField(max_length=20, default=STATUS_SIMULATED)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['scheduled_at']

    def __str__(self):
        return f"SMS for {self.booking} at {self.scheduled_at}"


class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='review')
    rating = models.PositiveSmallIntegerField()  # 1-5
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review for {self.booking} - {self.rating} stars"

    def star_range(self):
        return range(1, 6)


class CustomerNote(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='customer_notes')
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notes_about')
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Note about {self.customer.username} for {self.business.name}"
