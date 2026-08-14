# ERP-Final — Operations, Finance & HR Platform

[![Backend CI](https://github.com/MatiViglianco/ERP-Final/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/MatiViglianco/ERP-Final/actions/workflows/backend-ci.yml)

Internal ERP built to connect operational data that would otherwise remain split across spreadsheets, bank exports and isolated administrative workflows. The application covers sales and weighing, expenses, banking, accounts receivable, billing and collections, payroll, OCR-assisted voucher entry and multi-branch reporting.

**Stack:** Django 5, Django REST Framework, React 18, PostgreSQL, Material UI, Playwright, Docker and GitHub Actions.

> This public repository contains application code and sanitized configuration only. It does not include production records, credentials, certificates or customer data.

## Product scope

- **Sales and weighing:** CSV imports, daily sales, product trends, batch history and branch-level reporting.
- **Banking and expenses:** bank-statement imports, expense classification, assignments and financial dashboards.
- **Accounts receivable:** customer aliases, transaction history, partial payments, status calculation and statistics.
- **Billing and collections:** invoice previews, account-debt invoicing, Getnet imports/webhooks, terminal-to-branch mapping and payments that require review.
- **Payroll:** employees, aliases, remuneration sources, bank-transfer matching, account deductions, monthly summaries and aguinaldo calculations.
- **OCR voucher workflow:** image preparation, AI-assisted extraction, customer suggestions, human review and traceable import batches.
- **Multi-branch operation:** historical data backfill and branch-scoped queries across operational modules.

## Engineering highlights

- **86 backend tests** covering calculations, imports, billing, payroll, OCR, migrations and multi-branch isolation.
- Idempotent Getnet and bank-import flows that avoid duplicating external events.
- Human review for ambiguous OCR, payment and identity matches.
- Cookie-based JWT authentication with short-lived access tokens and rotating refresh flow.
- Production upgrade tests that verify historical data remains preserved during schema changes.
- PostgreSQL-backed CI, frontend builds and Playwright end-to-end coverage.
- Fiscal authorization isolated behind a provider boundary; `ARCA_PROVIDER=mock` is the safe default.

## Architecture

```mermaid
flowchart LR
    U["Authenticated operator"] --> R["React + Material UI"]
    R --> A["Django REST API"]
    A --> P[("PostgreSQL")]
    A --> O["OCR provider"]
    A --> G["Getnet imports / webhook"]
    A --> F["Fiscal provider boundary"]
    C["GitHub Actions"] --> T["Django tests + frontend build"]
    T --> D["Docker / Dokploy deployment"]
```

The backend owns business rules and data isolation. The React client consumes authenticated REST endpoints and does not make fiscal, accounting or matching decisions independently.

## Screens

![ERP dashboard](https://raw.githubusercontent.com/MatiViglianco/portfolio-astro/main/src/assets/erp1.jpg)

Additional product views are available in the [professional portfolio](https://mativiglianco.github.io/portfolio-astro/#projects).

## Live surfaces

- [Authenticated frontend](https://mativiglianco.github.io/ERP-Final/)
- [OCR voucher frontend](https://vales.mativiglianco.cloud/)
- Backend API: `https://api.mativiglianco.cloud/api`

The live applications require authorized credentials. Public visitors can review the architecture, tests and implementation in this repository without accessing business data.

## Local development

### Requirements

- Python 3.11+
- Node.js 22+
- PostgreSQL 16 recommended; SQLite is available for lightweight local work

### Backend

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Create a root `.env` file when you need non-default local values:

```dotenv
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True
DATABASE_URL=postgresql://erp:erp@localhost:5432/erp
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173
ARCA_PROVIDER=mock
OCR_PROVIDER=mock
```

Never commit secrets. Configure `GEMINI_API_KEY`, production database credentials, webhook secrets and fiscal certificates only in the deployment environment.

### Frontend

```powershell
cd frontend
npm ci
$env:VITE_API_BASE_URL='http://localhost:8000/api'
npm run dev
```

The development client runs at `http://localhost:5173`.

## Verification

```powershell
# Backend checks
python manage.py check
python manage.py test

# Frontend production build
cd frontend
npm ci
npm run build

# End-to-end suite (requires the configured test services)
npm run test:e2e
```

GitHub Actions runs the Django suite against PostgreSQL 16 for every pull request to `main`. Successful main-branch CI can trigger the guarded Dokploy deployment workflow.

## Production deployment

- `Dockerfile.backend` builds the Django/Gunicorn service.
- `dokploy.yaml` declares the backend service and persistent static volume.
- `.github/workflows/backend-ci.yml` runs Django checks and tests.
- `.github/workflows/deploy-frontend.yml` builds and publishes the React client to GitHub Pages.
- `.github/workflows/deploy-backend-dokploy.yml` deploys a successful main-branch revision to Dokploy.

Real ARCA/WSFE authorization is intentionally not enabled by default. Activation requires the correct certificate, service association, tax regime and point-of-sale configuration; until then, keep `ARCA_PROVIDER=mock`.

## Repository map

```text
ERP-Final/
├── backend/                 # Django project settings and root URLs
├── statsapp/                # Models, APIs, services, migrations and tests
│   └── tests/               # 86 backend regression tests
├── frontend/                # React/Vite client and Playwright E2E tests
├── .github/workflows/       # CI and deployment pipelines
├── Dockerfile.backend
├── dokploy.yaml
└── manage.py
```

## Contact

- [Matías Viglianco on LinkedIn](https://www.linkedin.com/in/mat%C3%ADas-agust%C3%ADn-viglianco/)
- [Professional portfolio](https://mativiglianco.github.io/portfolio-astro/)
- [GitHub profile](https://github.com/MatiViglianco)
