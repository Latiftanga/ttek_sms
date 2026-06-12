# TTEK SMS — School Management System

A multi-tenant school management system built with Django.

---

## Local Development Setup

### Prerequisites

- Docker & Docker Compose

### Start the dev server

```bash
docker compose up -d
```

The app will be available at `http://localhost:8000`.

On first start the entrypoint automatically runs migrations and sets up the public tenant.

---

## First-Time Platform Setup

### 1. Create the superuser

```bash
docker compose exec web python manage.py setup_public_tenant \
  --email admin@localhost \
  --password Admin@2026
```

### 2. Create a school (tenant)

Log into the Django admin at `http://localhost:8000/admin/` with the superuser credentials and create a **School** entry, e.g.:

| Field | Basic school example | SHS example |
|---|---|---|
| Name | Demo Basic School | Demo SHS |
| Schema name | `basic` | `shs` |
| Short name | DBS | DSHS |
| Primary domain | `basic.localhost` | `shs.localhost` |

### 3. Seed the school with demo data

**Basic school:**
```bash
docker compose exec web python manage.py populate_basic_demo_data "Demo Basic School"
```

**SHS:**
```bash
docker compose exec web python manage.py populate_shs_demo_data "Demo SHS"
```

You can also control how many students are generated per class:
```bash
docker compose exec web python manage.py populate_basic_demo_data "Demo Basic School" --students-per-class 15
```

---

## Default Demo Credentials

After seeding, access the school at `http://<domain>:8000` (e.g. `http://basic.localhost:8000`).

| Role | Email | Password |
|---|---|---|
| School Admin | `admin@<domain>` | `Demo@2026` |
| Teachers | `firstname.lastname@<domain>` | `Teacher@2026` |

Example for a school with domain `basic.localhost`:
- Admin: `admin@basic.localhost` / `Demo@2026`
- Teacher: `kwame.asante@basic.localhost` / `Teacher@2026`

---

## Resetting a Password

**Superuser (platform admin):**
```bash
docker compose exec web python manage.py changepassword <username>
```

**Find superuser usernames:**
```bash
docker compose exec web python manage.py shell -c \
  "from django.contrib.auth import get_user_model; [print(u.username, u.email) for u in get_user_model().objects.filter(is_superuser=True)]"
```

---

## Useful Commands

```bash
# List all tenant schools
docker compose exec web python manage.py shell -c \
  "from schools.models import School; [print(s.schema_name, '|', s.name) for s in School.objects.exclude(schema_name='public')]"

# Run migrations
docker compose exec web python manage.py migrate_schemas --shared
docker compose exec web python manage.py migrate_schemas --tenant

# Open a Django shell
docker compose exec web python manage.py shell

# View logs
docker compose logs -f web
```
