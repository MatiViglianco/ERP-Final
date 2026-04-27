# ERP Final

Proyecto ERP con backend Django y frontend React.

## Requisitos

- Python 3.10+
- Node.js 18+
- Pip + venv

## Backend Django

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r ../requirements.txt
python ..\manage.py migrate
python ..\manage.py createsuperuser
python ..\manage.py runserver
```

## Frontend ERP

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

## Produccion

Backend ERP:

```text
https://api.mativiglianco.cloud/api
```

Frontend de vales:

```text
https://vales.mativiglianco.cloud/
```

Variables productivas esperadas:

```text
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=api.mativiglianco.cloud
CORS_ALLOWED_ORIGINS=https://api.mativiglianco.cloud,https://vales.mativiglianco.cloud,https://mativiglianco.github.io
CSRF_TRUSTED_ORIGINS=https://api.mativiglianco.cloud,https://vales.mativiglianco.cloud,https://mativiglianco.github.io
OCR_PROVIDER=gemini
GEMINI_OCR_MODEL=gemini-3-flash-preview
GEMINI_THINKING_BUDGET=0
GUNICORN_TIMEOUT=240
GUNICORN_WORKERS=2
```

## OCR con Gemini

Configura `GEMINI_API_KEY` solo como variable de entorno en la VPS o en Dokploy. No la hardcodees en el repositorio.

## Primer login

1. Crea el superusuario (`createsuperuser`).
2. Inicia sesion en el frontend con esas credenciales.

## Scripts utiles

- Build frontend ERP: `cd frontend && npm run build`
- Pruebas backend: `python manage.py test`
