"""
Management command: python manage.py seed_demo
Creates fictional demo data for BookMtaani. Safe to re-run.
"""
import random
from datetime import datetime, date, time, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone


class Command(BaseCommand):
    help = 'Seeds demo data for BookMtaani. Safe to re-run (deletes and recreates demo data).'

    def handle(self, *args, **options):
        from core.models import (
            UserProfile, Business, BusinessHours, Service, TimeBlock,
            Booking, Payment, SMSNotification, Review, CustomerNote,
        )

        self.stdout.write("Clearing old demo data...")
        self._clear_demo_data()

        self.stdout.write("Creating demo accounts...")
        customer_user = self._create_user('demo_customer', 'Customer123!', 'Demo', 'Customer', False, 'customer')
        owner_user = self._create_user('demo_owner', 'Owner123!', 'Demo', 'Owner', False, 'owner')
        admin_user = self._create_user('demo_admin', 'Admin123!', 'Demo', 'Admin', True, 'owner')

        # Extra fictional customers for bookings
        extra_customers = []
        fictional_customers = [
            ('alice_wanjiru', 'Alice', 'Wanjiru'),
            ('brian_omondi', 'Brian', 'Omondi'),
            ('cynthia_achieng', 'Cynthia', 'Achieng'),
            ('david_kamau', 'David', 'Kamau'),
            ('esther_wambui', 'Esther', 'Wambui'),
            ('felix_otieno', 'Felix', 'Otieno'),
            ('grace_muthoni', 'Grace', 'Muthoni'),
            ('henry_kipchoge', 'Henry', 'Kipchoge'),
        ]
        for uname, fname, lname in fictional_customers:
            u = self._create_user(uname, 'Demo1234!', fname, lname, False, 'customer')
            extra_customers.append(u)

        self.stdout.write("Creating businesses...")
        businesses_data = [
            {
                'name': 'Kisii Kinyozi',
                'category': 'kinyozi',
                'town': 'Kisii',
                'description': 'Expert barbers in the heart of Kisii. Fades, shaves and more.',
                'phone': '+254711100001',
                'owner': owner_user,
                'services': [
                    ('Haircut', 300, 30, 'Classic and modern cuts'),
                    ('Shave', 150, 20, 'Hot towel shave'),
                    ('Fade', 350, 45, 'Skin and taper fades'),
                    ('Kids Haircut', 200, 25, 'For children under 12'),
                ],
                'hours': [(0,time(8,0),time(19,0)),(1,time(8,0),time(19,0)),(2,time(8,0),time(19,0)),(3,time(8,0),time(19,0)),(4,time(8,0),time(19,0)),(5,time(8,0),time(20,0)),(6,time(9,0),time(17,0))],
            },
            {
                'name': "Grace's Salon",
                'category': 'salon',
                'town': 'Kisii',
                'description': 'Professional hair care and styling in Kisii.',
                'phone': '+254711100002',
                'owner': admin_user,
                'services': [
                    ('Wash & Set', 500, 60, 'Shampoo, condition and style'),
                    ('Blowout', 400, 45, 'Professional blow dry'),
                    ('Relaxer', 800, 90, 'Hair relaxer treatment'),
                    ('Braiding', 1200, 120, 'Box braids and cornrows'),
                    ('Trim', 300, 30, 'Hair trim and shape'),
                ],
                'hours': [(0,time(8,0),time(18,0)),(1,time(8,0),time(18,0)),(2,time(8,0),time(18,0)),(3,time(8,0),time(18,0)),(4,time(8,0),time(18,0)),(5,time(8,0),time(19,0)),(6,time(9,0),time(16,0))],
            },
            {
                'name': 'CleanRight Laundry',
                'category': 'laundry',
                'town': 'Kisii',
                'description': 'Fast, affordable laundry services. We pick up and deliver.',
                'phone': '+254711100003',
                'owner': admin_user,
                'services': [
                    ('Wash & Dry', 400, 60, 'Per load, wash and dry'),
                    ('Wash, Dry & Fold', 550, 90, 'Full service laundry'),
                    ('Ironing', 200, 30, 'Per bundle of 10 items'),
                    ('Dry Clean (Suit)', 600, 60, 'Suit dry cleaning'),
                ],
                'hours': [(0,time(7,0),time(18,0)),(1,time(7,0),time(18,0)),(2,time(7,0),time(18,0)),(3,time(7,0),time(18,0)),(4,time(7,0),time(18,0)),(5,time(7,0),time(18,0)),(6,None,None)],
                'closed_days': [6],
            },
            {
                'name': 'SparkleWash Car Wash',
                'category': 'car_wash',
                'town': 'Nairobi',
                'description': 'Premium car wash in Nairobi. Exterior, interior, and detailing.',
                'phone': '+254711100004',
                'owner': admin_user,
                'services': [
                    ('Exterior Wash', 500, 30, 'Full exterior wash and rinse'),
                    ('Interior Vacuum', 300, 30, 'Full interior vacuum'),
                    ('Full Detail', 1500, 90, 'Complete inside and out'),
                    ('Wax & Polish', 1000, 60, 'Wax and polish exterior'),
                ],
                'hours': [(0,time(7,0),time(19,0)),(1,time(7,0),time(19,0)),(2,time(7,0),time(19,0)),(3,time(7,0),time(19,0)),(4,time(7,0),time(19,0)),(5,time(7,0),time(20,0)),(6,time(8,0),time(18,0))],
            },
            {
                'name': 'Zen Spa',
                'category': 'spa',
                'town': 'Nairobi',
                'description': 'Relaxation and wellness in the heart of Nairobi.',
                'phone': '+254711100005',
                'owner': admin_user,
                'services': [
                    ('Swedish Massage (60 min)', 2500, 60, 'Full body relaxation massage'),
                    ('Deep Tissue (60 min)', 3000, 60, 'Therapeutic deep tissue'),
                    ('Facial', 1800, 60, 'Deep cleansing facial'),
                    ('Mani-Pedi Combo', 1200, 60, 'Manicure and pedicure'),
                    ('Hot Stone Massage', 3500, 75, 'Heated stones for deep relaxation'),
                ],
                'hours': [(0,time(9,0),time(20,0)),(1,time(9,0),time(20,0)),(2,time(9,0),time(20,0)),(3,time(9,0),time(20,0)),(4,time(9,0),time(21,0)),(5,time(9,0),time(21,0)),(6,time(10,0),time(18,0))],
            },
            {
                'name': 'NailArt by Brenda',
                'category': 'nail_tech',
                'town': 'Mombasa',
                'description': 'Creative nail art and care in Mombasa.',
                'phone': '+254711100006',
                'owner': admin_user,
                'services': [
                    ('Basic Manicure', 500, 45, 'File, buff and paint'),
                    ('Gel Nails', 1200, 90, 'Gel overlay or tips'),
                    ('Acrylic Full Set', 1500, 90, 'Acrylic nail extensions'),
                    ('Nail Art', 800, 60, 'Custom nail art designs'),
                    ('Pedicure', 700, 60, 'Foot soak, scrub and paint'),
                ],
                'hours': [(0,time(9,0),time(18,0)),(1,time(9,0),time(18,0)),(2,time(9,0),time(18,0)),(3,time(9,0),time(18,0)),(4,time(9,0),time(18,0)),(5,time(9,0),time(19,0)),(6,None,None)],
                'closed_days': [6],
            },
            {
                'name': 'FitLife Gym',
                'category': 'fitness',
                'town': 'Kisii',
                'description': 'Personal training and fitness coaching in Kisii.',
                'phone': '+254711100007',
                'owner': admin_user,
                'services': [
                    ('Personal Training Session', 1000, 60, '1-on-1 with certified trainer'),
                    ('Group Fitness Class', 300, 60, 'Aerobics, zumba, HIIT'),
                    ('Nutrition Consultation', 800, 45, 'Diet and fitness planning'),
                ],
                'hours': [(0,time(6,0),time(21,0)),(1,time(6,0),time(21,0)),(2,time(6,0),time(21,0)),(3,time(6,0),time(21,0)),(4,time(6,0),time(21,0)),(5,time(7,0),time(20,0)),(6,time(8,0),time(16,0))],
            },
            {
                'name': 'Urban Cuts',
                'category': 'kinyozi',
                'town': 'Nakuru',
                'description': 'Trendy cuts and styles for the modern gentleman in Nakuru.',
                'phone': '+254711100008',
                'owner': admin_user,
                'services': [
                    ('Classic Cut', 300, 30, 'Traditional haircut'),
                    ('Skin Fade', 400, 45, 'High skin fade'),
                    ('Beard Trim', 200, 20, 'Beard shape and trim'),
                    ('Cut & Beard', 500, 50, 'Haircut plus beard trim'),
                ],
                'hours': [(0,time(8,0),time(19,0)),(1,time(8,0),time(19,0)),(2,time(8,0),time(19,0)),(3,time(8,0),time(19,0)),(4,time(8,0),time(19,0)),(5,time(8,0),time(20,0)),(6,time(9,0),time(17,0))],
            },
            {
                'name': 'Blossom Beauty',
                'category': 'salon',
                'town': 'Mombasa',
                'description': 'Complete beauty services for women in Mombasa.',
                'phone': '+254711100009',
                'owner': admin_user,
                'services': [
                    ('Hair Coloring', 1500, 90, 'Full head color treatment'),
                    ('Keratin Treatment', 3000, 120, 'Smoothing treatment'),
                    ('Cornrows', 800, 60, 'Traditional cornrow braiding'),
                    ('Makeup Application', 1200, 60, 'Full face makeup'),
                    ('Eyebrow Threading', 150, 15, 'Eyebrow shaping'),
                ],
                'hours': [(0,time(8,0),time(18,0)),(1,time(8,0),time(18,0)),(2,time(8,0),time(18,0)),(3,time(8,0),time(18,0)),(4,time(8,0),time(18,0)),(5,time(8,0),time(20,0)),(6,time(9,0),time(16,0))],
            },
        ]

        verified_indices = {0, 1, 3, 4, 6}  # businesses that are verified
        created_businesses = []
        for idx, bdata in enumerate(businesses_data):
            b = Business.objects.create(
                owner=bdata['owner'],
                name=bdata['name'],
                category=bdata['category'],
                town=bdata['town'],
                description=bdata['description'],
                phone=bdata['phone'],
                is_verified=(idx in verified_indices),
            )
            created_businesses.append(b)

            # Create hours
            closed_days = bdata.get('closed_days', [])
            for day, open_t, close_t in bdata['hours']:
                is_closed = day in closed_days
                BusinessHours.objects.create(
                    business=b,
                    day_of_week=day,
                    open_time=None if is_closed else open_t,
                    close_time=None if is_closed else close_t,
                    is_closed=is_closed,
                )

            # Create services
            for sname, sprice, sdur, sdesc in bdata['services']:
                Service.objects.create(
                    business=b,
                    name=sname,
                    price=sprice,
                    duration_minutes=sdur,
                    description=sdesc,
                )

        self.stdout.write(f"Created {len(created_businesses)} businesses.")

        self.stdout.write("Creating past bookings (60-100)...")
        all_customers = extra_customers + [customer_user]
        self._seed_bookings(created_businesses, all_customers)

        self.stdout.write("Done! Demo data seeded successfully.")
        self.stdout.write("\nDemo accounts:")
        self.stdout.write("  Customer: demo_customer / Customer123!")
        self.stdout.write("  Owner:    demo_owner / Owner123!")
        self.stdout.write("  Admin:    demo_admin / Admin123!")

    def _create_user(self, username, password, first, last, is_staff, role):
        from core.models import UserProfile
        # Delete if exists
        User.objects.filter(username=username).delete()
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first,
            last_name=last,
            is_staff=is_staff,
            is_superuser=is_staff,
            email=f"{username}@demo.bookmtaani.local",
        )
        UserProfile.objects.create(user=user, role=role)
        return user

    def _clear_demo_data(self):
        from core.models import UserProfile, Business
        demo_usernames = [
            'demo_customer', 'demo_owner', 'demo_admin',
            'alice_wanjiru', 'brian_omondi', 'cynthia_achieng',
            'david_kamau', 'esther_wambui', 'felix_otieno',
            'grace_muthoni', 'henry_kipchoge',
        ]
        User.objects.filter(username__in=demo_usernames).delete()
        # Clear businesses owned by deleted users (cascade) + others
        Business.objects.all().delete()

    def _seed_bookings(self, businesses, customers):
        from core.models import Service, Booking, Review, SMSNotification
        import uuid as _uuid

        today = timezone.localtime(timezone.now()).date()
        rng = random.Random(42)  # Deterministic seed

        total_created = 0
        reviews_created = 0

        for business in businesses:
            services = list(Service.objects.filter(business=business))
            if not services:
                continue

            # Create 8-12 past bookings per business
            num_bookings = rng.randint(8, 12)
            for _ in range(num_bookings):
                # Realistic pattern: more on weekends (Sat=5, Sun=6), evenings
                days_back = rng.randint(1, 90)
                booking_date = today - timedelta(days=days_back)

                # Skew toward weekends
                if rng.random() < 0.4:
                    # Pick a Sat or Sun in the range
                    weekend_offset = (5 - booking_date.weekday()) % 7
                    booking_date = booking_date + timedelta(days=weekend_offset)
                    if booking_date >= today:
                        booking_date = today - timedelta(days=1)

                service = rng.choice(services)
                customer = rng.choice(customers)

                # Get hours for this day
                from core.models import BusinessHours
                try:
                    bh = BusinessHours.objects.get(business=business, day_of_week=booking_date.weekday())
                except BusinessHours.DoesNotExist:
                    continue

                if bh.is_closed or not bh.open_time:
                    continue

                # Skew toward evening (5-8pm)
                open_hour = bh.open_time.hour
                close_hour = bh.close_time.hour
                duration_h = service.duration_minutes // 60
                slots_available = []
                h = open_hour
                while h + (service.duration_minutes / 60) <= close_hour:
                    slots_available.append(h)
                    h += service.duration_minutes // 60 or 1

                if not slots_available:
                    continue

                # Prefer hours 17-19 (5-7pm) for evening pattern
                evening_slots = [h for h in slots_available if 17 <= h <= 19]
                morning_slots = [h for h in slots_available if 9 <= h <= 11]
                if booking_date.weekday() >= 5 and evening_slots and rng.random() < 0.5:
                    hour = rng.choice(evening_slots)
                elif morning_slots and rng.random() < 0.3:
                    hour = rng.choice(morning_slots)
                else:
                    hour = rng.choice(slots_available)

                minute = rng.choice([0, 30]) if service.duration_minutes <= 30 else 0
                start_time = time(hour, minute)

                from datetime import datetime as dt, timedelta as td
                start_dt = dt.combine(booking_date, start_time)
                end_dt = start_dt + td(minutes=service.duration_minutes)
                end_time = end_dt.time()

                # Check no overlap with existing bookings
                overlap = Booking.objects.filter(
                    service__business=business,
                    date=booking_date,
                    status__in=('confirmed', 'completed'),
                ).filter(
                    start_time__lt=end_time,
                    end_time__gt=start_time,
                ).exists()

                if overlap:
                    continue

                # Determine status (mostly completed since in past)
                status_weights = [
                    (Booking.STATUS_COMPLETED, 0.6),
                    (Booking.STATUS_CONFIRMED, 0.15),
                    (Booking.STATUS_NO_SHOW, 0.1),
                    (Booking.STATUS_CANCELLED, 0.15),
                ]
                r = rng.random()
                cumulative = 0
                status = Booking.STATUS_COMPLETED
                for s, w in status_weights:
                    cumulative += w
                    if r <= cumulative:
                        status = s
                        break

                booking = Booking.objects.create(
                    customer=customer,
                    service=service,
                    date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    status=status,
                )
                total_created += 1

                # Add review for completed bookings (60% chance)
                if status == Booking.STATUS_COMPLETED and rng.random() < 0.6:
                    rating = rng.choices([3, 4, 5], weights=[1, 3, 5])[0]
                    comments = [
                        "Great service, very professional!",
                        "Will definitely come back.",
                        "Good job, satisfied with the results.",
                        "Fast and clean, recommended.",
                        "Excellent work, friendly staff.",
                        "Decent service for the price.",
                        "Very happy with the outcome!",
                        "",  # No comment
                    ]
                    Review.objects.create(
                        booking=booking,
                        rating=rating,
                        comment=rng.choice(comments),
                    )
                    reviews_created += 1

        # Create a few future bookings for the demo customer
        for business in businesses[:3]:
            services = list(Service.objects.filter(business=business))
            if not services:
                continue
            service = services[0]

            # Next available weekday
            future_date = today + timedelta(days=rng.randint(1, 7))
            # Ensure it's a weekday
            while future_date.weekday() == 6:  # Skip Sunday if closed for some
                future_date += timedelta(days=1)

            from core.models import BusinessHours
            try:
                bh = BusinessHours.objects.get(business=business, day_of_week=future_date.weekday())
            except BusinessHours.DoesNotExist:
                continue
            if bh.is_closed or not bh.open_time:
                continue

            start_time = time(bh.open_time.hour + 1, 0)
            if start_time >= bh.close_time:
                continue

            from datetime import datetime as dt, timedelta as td
            end_dt = dt.combine(future_date, start_time) + td(minutes=service.duration_minutes)
            end_time = end_dt.time()

            existing = Booking.objects.filter(
                service__business=business,
                date=future_date,
                start_time=start_time,
                status__in=('pending', 'confirmed'),
            ).exists()
            if not existing:
                b = Booking.objects.create(
                    customer=customers[0],  # demo_customer
                    service=service,
                    date=future_date,
                    start_time=start_time,
                    end_time=end_time,
                    status=Booking.STATUS_CONFIRMED,
                )
                total_created += 1

                # SMS notifications
                from core.services import create_sms_notifications
                create_sms_notifications(b)

        self.stdout.write(f"Created {total_created} bookings, {reviews_created} reviews.")
