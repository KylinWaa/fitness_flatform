
# Fitness Platform (锻体打卡)

A gamified fitness check-in web application to help you stay consistent with your workout routine. Built with Flask + SQLite, mobile-first responsive design.

## Features

- **Daily Check-in** — Start and end your workout sessions with a timer. Tracks duration automatically.
- **Weekly Schedule** — Set which days of the week you commit to working out. Modified once per month.
- **Gamification** — Earn **makeup tokens** for 7-day streaks (use them to backfill missed days). Miss a scheduled day? Get penalized (deducted from your balance).
- **Public Account** — Penalties go to a shared pool. Transfer money to other users or the pool.
- **Rankings & Battle** — Compete with others by check-in rate, streak, and monthly volume.
- **Push Notifications** — Integrate with [Bark](https://day.app) for iOS push notifications (reminders at 8 PM, workout start/end alerts, penalty warnings).
- **Admin Panel** — User management, balance/penalty editing, password reset.
- **Public API** — Start/end check-ins via URL (`/api/username=<name>/start`) for external integrations.
- **Mobile-first** — Optimized for mobile browsers with iOS-style UI.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3, Flask 3.1 |
| Database | SQLite via SQLAlchemy |
| Auth | Flask-Login + Werkzeug |
| Frontend | Server-rendered Jinja2 templates, vanilla JS, Font Awesome 6 |
| Push | Bark (iOS push notification HTTP API) |

## Quick Start

```bash
# Clone
git clone https://github.com/KylinWaa/fitness_flatform.git
cd fitness_flatform

# Install dependencies
pip install -r requirements.txt

# Run (database auto-initializes with admin/admin)
python app.py
```

Open `http://localhost:5000` and log in with:
- **Default admin**: `admin` / `admin`

## Project Structure

```
fitness_flatform/
├── app.py                 # Flask application (routes, API, helpers)
├── models.py              # SQLAlchemy ORM models
├── requirements.txt       # Python dependencies
├── bark_icon.png          # Custom icon for push notifications
├── static/
│   ├── css/style.css      # Mobile-first responsive stylesheet
│   └── js/main.js         # Timer and UI interactions
└── templates/
    ├── base.html          # Layout template with bottom nav
    ├── login.html         # Login page
    ├── register.html      # Registration
    ├── dashboard.html     # Main dashboard with stats
    ├── checkin.html       # Workout check-in page
    ├── schedule.html      # Weekly schedule + Bark settings
    ├── rankings.html      # User rankings
    ├── battle.html        # User vs user comparison
    ├── records.html       # Check-in history with filters
    ├── transactions.html  # Transaction history
    └── admin.html         # Admin panel
```

## API Endpoints

### Pages (HTML)

| Route | Description |
|-------|-------------|
| `/` | Dashboard |
| `/login` | Login |
| `/register` | Register |
| `/checkin` | Check-in with timer |
| `/schedule` | Schedule + Bark bind |
| `/rankings` | Rankings |
| `/battle` | User comparison |
| `/records` | Records with filters |
| `/transactions` | Transaction history |
| `/admin` | Admin panel |

### JSON API

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/checkin/start` | Start a check-in |
| POST | `/api/checkin/end` | End a check-in |
| DELETE | `/api/checkin/<id>` | Delete today's check-in |
| POST | `/api/schedule/update` | Update weekly schedule |
| POST | `/api/bark/bind` | Bind/unbind Bark push key |
| POST | `/api/makeup/use` | Use a makeup token |
| POST | `/api/settlement/run` | Run penalty settlement |
| POST | `/api/remind` | Send reminders (cron: 8 PM) |
| POST | `/api/transfer` | Transfer money |
| GET | `/api/stats/<user_id>` | Get user stats |
| GET/POST | `/api/username=<name>/start` | Public check-in start |
| GET/POST | `/api/username=<name>/end` | Public check-in end |

## Deployment

The app runs on port 5000 by default. For production:

- Use **systemd** for process management (service file included in deployment).
- Use **Nginx/Caddy** as a reverse proxy for HTTPS termination.
- Set up a cron job to hit `/api/remind` at 8 PM daily for reminders.
- Place a custom `bark_icon.png` in the app root for push notification icons.

## License

MIT
