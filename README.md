# BookMtaani

**Digital booking platform for small service businesses in Kenya.**

Built as a hackathon demo for the **AI Hackathon, Kisii National Polytechnic, 11–13 November 2026**.
Track: Digital Transformation. Theme: Sustainability and Future Green Jobs.

> **WARNING: Local demo only. Do NOT deploy this publicly as-is.**
> Secret keys are hardcoded, passwords are weak, and the system uses SQLite.
> See "Next Steps" for a production-ready path.

---

## What is BookMtaani?

BookMtaani lets customers in Kenya book appointments at small local businesses — kinyozis, salons,
laundries, car washes, spas, nail technicians, and fitness trainers. Businesses manage their
schedules, pricing, and customers through an owner dashboard.

---

## How to Run

**Requirements:** Python 3.10+ and pip.

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Apply database migrations
python manage.py migrate

# 3. Seed demo data (creates demo accounts + fictional businesses and bookings)
python manage.py seed_demo

# 4. Start the development server
python manage.py runserver

# 5. Open in your browser
# http://localhost:8000/
```

The app runs fully offline — all CSS, fonts, and JavaScript are bundled locally.

---

## Demo Accounts

| Role     | Username        | Password      |
|----------|-----------------|---------------|
| Customer | demo_customer   | Customer123!  |
| Owner    | demo_owner      | Owner123!     |
| Admin    | demo_admin      | Admin123!     |

The admin account also has access to Django admin at `/django-admin/`.

---

## What is Simulated

- **M-Pesa payments**: Fake STK push screen. Enter any PIN except `0000` to simulate success. Use `0000` to simulate failure. No real money moves.
- **SMS reminders**: Generated as in-app notification records; no real SMS is sent.
- **AI busy-time insight**: Rule-based statistical analysis of seed booking data. No external AI service used.
- **All seed data**: Fictional businesses, customers, and booking history. No real personal information.

---

## Django Admin

Visit `/django-admin/` and log in as `demo_admin`.

- **Verify businesses**: Go to Businesses, select, and use the "Verify selected businesses" action.
- **Manage users**: Via the Users section with UserProfile inline.

---

## Running Tests

```bash
python manage.py test
```

Tests cover:
- Available slot calculation
- Double-booking prevention
- Booking outside business hours is rejected
- Booking in the past is rejected
- Owner isolation (owner cannot access another owner's data)

---

## Project Structure

```
bookmtaani/
├── bookmtaani/        # Django project settings and URL root
├── core/              # Main app: models, views, services, admin
│   ├── management/commands/seed_demo.py
│   ├── services.py    # Booking logic (get_available_slots, create_booking)
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   └── tests/
├── templates/         # HTML templates
├── static/
│   ├── css/main.css
│   ├── js/chart.umd.min.js   (Chart.js, local)
│   └── fontawesome/          (Font Awesome Free 6.5.1, local)
├── requirements.txt
├── README.md
└── DEMO_SCRIPT.md
```

---

## Known Limitations

- SQLite database — not suitable for concurrent production use.
- No real authentication security (weak demo passwords, no 2FA, no rate limiting).
- No HTTPS; cookies are not secure for production.
- No image uploads for business profiles or staff photos.
- Seed data is re-created on each `seed_demo` run, wiping previous demo changes.
- Timezone handling is best-effort for SQLite (all datetimes stored as UTC, displayed in Africa/Nairobi).

---

## Next Steps (Production)

- **Real M-Pesa**: Integrate Safaricom Daraja API (STK Push, C2B callbacks).
- **Real SMS**: Africa's Talking SMS API for appointment reminders.
- **Production database**: PostgreSQL with connection pooling.
- **Security**: Strong secret key from environment, HTTPS, secure cookies, rate limiting, 2FA.
- **Hosting**: Railway, Render, or a VPS with Nginx + Gunicorn.
- **Data protection**: Comply with Kenya Data Protection Act 2019.
- **Testing with real businesses**: User research with Kisii kinyozis and salons before launch.
- **Complaint handling**: Dispute resolution flow.
- **Payment reconciliation**: Real payment records and receipts.
- **System monitoring**: Error tracking (Sentry), uptime monitoring.
- **Business onboarding**: Self-service registration, ID verification, onboarding guide.

---

*Built for hackathon demo purposes. All data is fictional.*
