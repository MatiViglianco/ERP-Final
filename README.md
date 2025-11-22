# ERP Final

Proyecto ERP con backend Django y frontend React (Vite + MUI).

## Requisitos
- Python 3.10+
- Node.js 18+
- Pip + venv

## Backend (Django)
```bash
cd backend
# activar entorno si existe
python -m venv .venv
.\.venv\Scripts\activate   # Windows
# instalar deps
pip install -r ../requirements.txt
# migraciones y superusuario
python ..\manage.py migrate
python ..\manage.py createsuperuser
# levantar servidor
python ..\manage.py runserver
```
Backend por defecto en `http://127.0.0.1:8000/`.

## Frontend (Vite)
```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```
Frontend en `http://localhost:5173/`.

## Variables y configuración
- API del frontend apunta a `http://localhost:8000/api`. Ajusta las constantes en `frontend/src/context/AuthContext.jsx` y páginas si cambias el host.
- Asegura que el backend permita CORS para el host del frontend si lo mueves.

## Primer login
1. Crea el superusuario (`createsuperuser`).
2. Inicia sesión en el frontend con esas credenciales.

## Scripts útiles
- Build frontend: `cd frontend && npm run build`
- Ejecutar pruebas backend (si las agregas): `python manage.py test`
