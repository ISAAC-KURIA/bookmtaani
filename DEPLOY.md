# BookMtaani — Complete Setup & Deployment Guide

Everything you need to get from a blank machine to a running demo, step by step.

---

## What you need before you start

| Requirement | Minimum version | How to check |
|---|---|---|
| Python | 3.10 | `python --version` |
| pip | ships with Python | `pip --version` |
| Git (optional) | any | `git --version` |

No Node.js, no npm, no Docker, no internet connection during the demo.
All CSS, fonts, and JavaScript are already bundled in the `static/` folder.

---

## Step 1 — Get the code onto your machine

**Option A — clone from Git**
```bash
git clone <your-repo-url> bookmtaani
cd bookmtaani
```

**Option B — copy the folder**
Copy the `bookmtaani` project folder to your machine. Open a terminal inside it.
```bash
cd path\to\bookmtaani
```

Confirm you are in the right place — you should see `manage.py` when you list files:
```
# Windows PowerShell
dir
# Mac / Linux
ls
```

---

## Step 2 — Create a virtual environment (recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac / Linux
python3 -m venv venv
source venv/bin/activate
```

Your terminal prompt will change to show `(venv)` when the environment is active.
Run all commands below inside this environment.

---

## Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs only one package: `Django 5.1.3`.
Everything else (Chart.js, Font Awesome) is already in `static/` and needs no installation.

---

## Step 4 — Create the database

```bash
python manage.py migrate
```

This creates `db.sqlite3` in the project root with all tables.
No configuration needed — SQLite is built into Python.

---

## Step 5 — Load demo data

```bash
python manage.py seed_demo
```

This creates:
- 9 fictional businesses across Kisii, Nairobi, Mombasa, and Nakuru
- 89 past bookings with realistic weekend/evening patterns
- 31 reviews
- 3 demo accounts (see below)

The command is safe to re-run — it wipes and recreates all demo data.
Run it again between demo sessions to reset to a clean state.

---

## Step 6 — Start the server

```bash
python manage.py runserver
```

Open your browser at:
```
http://localhost:8000/
```

The app runs fully offline from this point. No internet required.

---

## Demo accounts

These are shown on the login page while in demo mode.

| Role | Username | Password | Access |
|---|---|---|---|
| Customer | `demo_customer` | `Customer123!` | Search, book, pay (simulated), reviews |
| Business Owner | `demo_owner` | `Owner123!` | Owner dashboard, schedule, analytics |
| Admin / Staff | `demo_admin` | `Admin123!` | Django admin + platform totals page |

Django admin panel is at:
```
http://localhost:8000/django-admin/
```
Log in with `demo_admin` / `Admin123!`

---

## Key URLs once the server is running

| Page | URL |
|---|---|
| Homepage / business search | `http://localhost:8000/` |
| Register new account | `http://localhost:8000/accounts/register/` |
| Login | `http://localhost:8000/accounts/login/` |
| My bookings (customer) | `http://localhost:8000/my-bookings/` |
| My notifications | `http://localhost:8000/notifications/` |
| Owner dashboard | `http://localhost:8000/owner/dashboard/` |
| Platform totals (staff) | `http://localhost:8000/admin/platform-totals/` |
| Django admin | `http://localhost:8000/django-admin/` |

---

## Running tests

```bash
python manage.py test
```

17 tests covering:
- Available slot calculation
- Double-booking prevention (two customers cannot book the same slot)
- Booking in the past is rejected
- Booking outside business hours is rejected
- Owner isolation (owner cannot access another owner's business data)

---

## Resetting between demo runs

```bash
python manage.py seed_demo
```

This wipes all demo data and recreates it fresh. Run it before each demo session.

---

## Project structure at a glance

```
bookmtaani/
│
├── manage.py                      ← Django entry point
├── requirements.txt               ← pip install -r this
├── db.sqlite3                     ← auto-created by migrate
│
├── bookmtaani/                    ← Django project package
│   ├── settings.py                ← timezone, database, static files
│   └── urls.py                    ← root URL config
│
├── core/                          ← main application
│   ├── models.py                  ← all 10 data models
│   ├── views.py                   ← all views (customer, owner, admin)
│   ├── forms.py                   ← all forms
│   ├── services.py                ← booking logic (get_available_slots, create_booking)
│   ├── admin.py                   ← Django admin config + verify action
│   ├── urls.py                    ← all URL patterns
│   ├── management/commands/
│   │   └── seed_demo.py           ← demo data command
│   └── tests/
│       └── test_booking.py        ← 17 automated tests
│
├── templates/                     ← HTML templates
│   ├── base.html                  ← site-wide layout + demo banner
│   └── ...
│
└── static/
    ├── css/main.css               ← all styles, brand color variables
    ├── js/chart.umd.min.js        ← Chart.js 4.4.0 (local, no CDN)
    └── fontawesome/               ← Font Awesome Free 6.5.1 (local, no CDN)
```

---

## What is simulated (not real)

| Feature | What actually happens |
|---|---|
| M-Pesa payment | Fake STK push screen. Any PIN except `0000` = success. `0000` = failure. No money moves. |
| SMS reminders | Stored as records in the database. Shown in the in-app Notifications page. No real SMS sent. |
| AI busy-time insight | Rule-based calculation from seed booking data. Labelled "Simulated insight". No external AI service. |
| All seed data | Fictional names, businesses, and booking history. No real personal information. |

---

## How to register a new user (starting from scratch)

1. Go to `http://localhost:8000/accounts/register/`
2. Fill in username, email, password, and select your role (Customer or Business Owner)
3. You are logged in immediately after registering
4. As a **Customer**: search for a business on the homepage, pick a service, choose a date and time, and complete the simulated M-Pesa flow
5. As a **Business Owner**: go to the Owner Dashboard at `http://localhost:8000/owner/dashboard/` — if you have no business yet, you will see a prompt to register one

---

## Troubleshooting

**"No module named django"**
You are not in the virtual environment. Run `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Mac/Linux) first.

**"Table doesn't exist" or database errors**
Run `python manage.py migrate` again.

**Static files (CSS, icons) not loading**
Make sure `DEBUG = True` in `bookmtaani/settings.py` (it is by default). The dev server serves static files automatically in debug mode.

**Port 8000 already in use**
Run on a different port: `python manage.py runserver 8080` then open `http://localhost:8080/`

**Changes to seed data not showing**
Run `python manage.py seed_demo` to reset, then refresh the browser.

---

## Security notice

> **This project is for local demo only. Do NOT deploy it publicly as-is.**
>
> - The secret key is hardcoded in `settings.py`
> - Passwords are intentionally weak for demo purposes
> - SQLite is not suitable for concurrent production use
> - `DEBUG = True` exposes detailed error pages
> - No HTTPS, no secure cookies, no rate limiting

See the "Next Steps" section in `README.md` for the production-ready path.

---

## Quick reference — all commands in order

```bash
# 1. Activate virtual environment (do this every new terminal session)
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac / Linux

# 2. Install dependencies (once)
pip install -r requirements.txt

# 3. Set up database (once, or after deleting db.sqlite3)
python manage.py migrate

# 4. Load demo data (run before each demo session to reset)
python manage.py seed_demo

# 5. Start the server
python manage.py runserver

# 6. Run tests
python manage.py test

# 7. Reset demo data between runs
python manage.py seed_demo
```
