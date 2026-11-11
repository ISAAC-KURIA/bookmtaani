# BookMtaani — Demo Script (3–5 minutes)

**Event:** AI Hackathon, Kisii National Polytechnic, 11–13 Nov 2026
**Track:** Digital Transformation | **Theme:** Sustainability & Future Green Jobs

---

## Before the Demo

1. Reset demo data: `python manage.py seed_demo`
2. Start the server: `python manage.py runserver`
3. Open two browser tabs: one for customer, one for owner/admin
4. Have a phone or second screen ready to show mobile responsiveness

---

## Part 1 — Admin Verifies a Business (~30 seconds)

1. Open `http://localhost:8000/accounts/login/`
2. Click the **Admin** demo account button to auto-fill, then sign in.
3. Go to `http://localhost:8000/django-admin/`
4. Click **Businesses** in the left sidebar.
5. Notice some businesses have **Verified = No**.
6. Select **CleanRight Laundry** and **NailArt by Brenda**.
7. In the Action dropdown, choose **"Verify selected businesses"**, click **Go**.
8. Show the **Verified** checkboxes are now ticked. ✓

> **Talk track:** "Business owners register their services. Our admin team verifies them so customers know they're legitimate — it's trust infrastructure for informal businesses."

---

## Part 2 — Customer Books an Appointment (~2 minutes)

### 2a. Register or sign in as customer

1. Open a new private/incognito tab (or sign out).
2. Go to `http://localhost:8000/accounts/register/`
3. Register as a new customer, or use the **Customer** demo button on the login page.

### 2b. Find a business

1. You'll land on the homepage — the business listing.
2. Use the **Category filter** to select **Kinyozi (Barber)**.
3. Click on **Kisii Kinyozi**.
4. Show the business page: services with KES prices, opening hours, and reviews.
5. Notice the **Verified** badge.

### 2c. Book a slot

1. Click **Book** next to **Haircut (KES 300)**.
2. Select tomorrow's date and click **Find Slots**.
3. The system shows only available slots — no double-booking possible.
4. Click a slot (e.g., **09:00**), then **Confirm Slot**.
5. Review the booking summary and click **Confirm Booking & Pay**.

### 2d. Simulated M-Pesa payment

1. The M-Pesa screen shows: "STK Push sent — enter your PIN".
2. Enter any 6-digit PIN (e.g., **123456**) and click **Pay KES 300**.
3. Show the brief "Processing…" spinner.
4. The confirmation page shows: booking reference, payment success (simulated), and two **simulated SMS reminders**.

> **Talk track:** "In production, this connects to Safaricom's Daraja API. Here it's simulated — no real money moves. The SMS reminders would go via Africa's Talking."

### 2e. My Bookings

1. Click **My Bookings** in the navigation.
2. Show the upcoming booking with status **Confirmed**.
3. Show cancel and reschedule options.

---

## Part 3 — Owner Approves and Sees Analytics (~1.5 minutes)

### 3a. Sign in as owner

1. Sign out, then sign in as **demo_owner / Owner123!**.
2. You land on the **Owner Dashboard**.

### 3b. Today's schedule and bookings

1. Show **Today's Schedule** — list of today's bookings in time order.
2. Click **Bookings** in the sidebar.
3. Find a **Pending** booking and click **Confirm**. Status changes to Confirmed.
4. Find a **Confirmed** booking and mark it **Complete**.

> **Talk track:** "Owners manage their whole day from here — no paper appointment books."

### 3c. Analytics

1. Click **Analytics** in the sidebar.
2. Show the stats bar: total bookings, completed, no-show rate, revenue.
3. Show the **Bookings Per Day** bar chart (blue bars, last 30 days).
4. Show the **Revenue Per Week** chart (green bars).
5. Show the **Busiest Hours** chart.
6. Highlight the **Simulated AI Insight** box:
   > "Saturdays around 17:00 are your busiest time — consider a discount on Tuesday mornings to increase bookings then."
7. Point out the label: **"Simulated AI insight (rule-based)"** — honest, no black-box AI.

> **Talk track:** "This is a rule-based statistical insight from booking history. In production, with more data, this could be a proper ML model — but we keep it transparent and labeled."

---

## Part 4 — Closing Points (~30 seconds)

> "BookMtaani digitises the booking experience for small businesses that currently rely on WhatsApp and walk-ins. The sustainability angle: paperless records, reduced no-shows through SMS reminders, and enabling these micro-businesses to participate in the digital economy — supporting future green jobs by keeping local services viable and efficient.

> The tech stack is Django with SQLite for the demo, and all integrations — M-Pesa, SMS, analytics — are real APIs we've identified for production. The business logic lives in one testable service layer."

---

## Reset Instructions

If you need to reset all demo data at any point:

```bash
python manage.py seed_demo
```

This safely deletes and recreates all demo businesses, bookings, and accounts.

---

## Q&A Prep

| Question | Answer |
|---|---|
| Is the M-Pesa real? | No — simulated for the demo. Production uses Safaricom Daraja API (STK Push). |
| What about data privacy? | Kenya Data Protection Act 2019 compliance is a production requirement. No real data is stored here. |
| Why Django? | Rapid prototyping, built-in admin, strong ecosystem. Production would add PostgreSQL, Nginx, and Gunicorn. |
| Can multiple owners use it? | Yes — each owner sees only their own business and bookings. Owner isolation is tested. |
| What's the green/sustainability angle? | Paperless records, reduced no-shows save time and fuel, digitisation enables sustainability reporting for micro-businesses. |
