from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Public
    path('', views.home, name='home'),
    path('business/<slug:slug>/', views.business_detail, name='business_detail'),

    # Auth
    path('accounts/login/', views.login_view, name='login'),
    path('accounts/logout/', views.logout_view, name='logout'),
    path('accounts/register/', views.register_view, name='register'),

    # Booking flow
    path('book/<int:service_id>/', views.booking_form, name='booking_form'),
    path('book/<int:service_id>/slots/', views.available_slots_json, name='available_slots'),
    path('book/<int:service_id>/confirm/<str:date>/<str:time>/', views.booking_confirm, name='booking_confirm'),
    path('booking/<int:booking_id>/mpesa/', views.mpesa_payment, name='mpesa_payment'),
    path('booking/<int:booking_id>/', views.booking_detail, name='booking_detail'),

    # Customer
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('booking/<int:booking_id>/cancel/', views.cancel_booking, name='cancel_booking'),
    path('booking/<int:booking_id>/reschedule/', views.reschedule_booking, name='reschedule_booking'),
    path('notifications/', views.notifications, name='notifications'),
    path('review/<int:booking_id>/', views.submit_review, name='submit_review'),

    # Owner
    path('owner/', views.owner_dashboard, name='owner_dashboard'),
    path('owner/bookings/', views.owner_bookings, name='owner_bookings'),
    path('owner/bookings/<int:booking_id>/action/', views.owner_booking_action, name='owner_booking_action'),
    path('owner/services/', views.owner_services, name='owner_services'),
    path('owner/services/add/', views.owner_service_add, name='owner_service_add'),
    path('owner/services/<int:service_id>/edit/', views.owner_service_edit, name='owner_service_edit'),
    path('owner/services/<int:service_id>/delete/', views.owner_service_delete, name='owner_service_delete'),
    path('owner/schedule/', views.owner_schedule, name='owner_schedule'),
    path('owner/schedule/block/add/', views.owner_block_add, name='owner_block_add'),
    path('owner/schedule/block/<int:block_id>/delete/', views.owner_block_delete, name='owner_block_delete'),
    path('owner/hours/', views.owner_hours, name='owner_hours'),
    path('owner/customers/', views.owner_customers, name='owner_customers'),
    path('owner/customers/<int:customer_id>/note/', views.owner_customer_note, name='owner_customer_note'),
    path('owner/analytics/', views.owner_analytics, name='owner_analytics'),
    path('owner/register/', views.owner_register_business, name='owner_register_business'),

    # Platform admin
    path('admin-platform/', views.platform_totals, name='platform_totals'),
]
