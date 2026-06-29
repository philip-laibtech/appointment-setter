# appointment-setter

A multi-tenant Django SaaS for service businesses: companies publish a
public booking page, customers book appointments without needing an
account, and companies manage staff, services, availability, and bookings
from a dashboard.

## Documentation

Full documentation lives in **[docs/](docs/README.md)**:

- **[docs/setup.md](docs/setup.md)** — local setup, running tests, project structure
- **[docs/deployment.md](docs/deployment.md)** — production deployment checklist
- **[docs/gdpr_compliance.md](docs/gdpr_compliance.md)** — GDPR architecture & runbooks
- **[docs/README.md](docs/README.md)** — full documentation index

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```
