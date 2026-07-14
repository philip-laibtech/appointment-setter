# appointment-setter

A multi-tenant Django SaaS for service businesses: companies publish a
public booking page, customers book appointments without needing an
account, and companies manage staff, services, availability, and bookings
from a dashboard.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```
