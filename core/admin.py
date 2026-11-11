from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import (
    UserProfile, Business, BusinessHours, Service, TimeBlock,
    Booking, Payment, SMSNotification, Review, CustomerNote
)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'


class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


def verify_businesses(modeladmin, request, queryset):
    queryset.update(is_verified=True)
verify_businesses.short_description = "Verify selected businesses"


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'town', 'owner', 'is_verified', 'created_at']
    list_filter = ['is_verified', 'category', 'town']
    search_fields = ['name', 'town', 'owner__username']
    actions = [verify_businesses]
    prepopulated_fields = {'slug': ('name',)}


@admin.register(BusinessHours)
class BusinessHoursAdmin(admin.ModelAdmin):
    list_display = ['business', 'day_of_week', 'open_time', 'close_time', 'is_closed']
    list_filter = ['business', 'is_closed']


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'business', 'price', 'duration_minutes', 'is_active']
    list_filter = ['business', 'is_active']
    search_fields = ['name', 'business__name']


@admin.register(TimeBlock)
class TimeBlockAdmin(admin.ModelAdmin):
    list_display = ['business', 'date', 'start_time', 'end_time', 'reason']
    list_filter = ['business', 'reason']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['customer', 'service', 'date', 'start_time', 'status', 'created_at']
    list_filter = ['status', 'date', 'service__business']
    search_fields = ['customer__username', 'service__name']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['booking', 'amount', 'method', 'status', 'transaction_ref', 'created_at']
    list_filter = ['status', 'method']


@admin.register(SMSNotification)
class SMSNotificationAdmin(admin.ModelAdmin):
    list_display = ['booking', 'scheduled_at', 'status']
    list_filter = ['status']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['booking', 'rating', 'created_at']
    list_filter = ['rating']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role']
    list_filter = ['role']


@admin.register(CustomerNote)
class CustomerNoteAdmin(admin.ModelAdmin):
    list_display = ['business', 'customer', 'created_at']
