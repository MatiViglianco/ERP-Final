import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

application = get_wsgi_application()

# Solo el servidor web carga este modulo (no migrate ni los tests): cada worker
# arranca su hilo de reintento de ARCA; un lock evita que corran a la vez.
from statsapp.arca_retry import start_retry_scheduler  # noqa: E402

start_retry_scheduler()
