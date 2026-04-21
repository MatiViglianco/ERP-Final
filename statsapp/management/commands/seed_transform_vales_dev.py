from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from statsapp.models import AccountClient, ValeImportBatch
from statsapp.vales_services import create_vale_batch, ensure_alias


User = get_user_model()


USERS = [
    {
        'username': 'monica',
        'password': 'carni2026',
        'first_name': 'Monica',
        'last_name': 'Carnicera',
        'is_staff': True,
        'is_superuser': True,
    },
    {
        'username': 'dario',
        'password': 'vales123',
        'first_name': 'Dario',
        'last_name': 'Operador',
        'is_staff': True,
        'is_superuser': False,
    },
]


CLIENTS = [
    {'external_id': 'C-0012', 'first_name': 'Silvina', 'last_name': 'Farias', 'phone': '+543584000001'},
    {'external_id': 'C-0034', 'first_name': 'Juan', 'last_name': 'Cornavilla', 'phone': '+543584000002'},
    {'external_id': 'C-0045', 'first_name': 'Ivano', 'last_name': 'Vera', 'phone': '+543584000003'},
    {'external_id': 'C-0051', 'first_name': 'Gadea', 'last_name': 'Rodriguez', 'phone': '+543584000004'},
    {'external_id': 'C-0067', 'first_name': 'Luis', 'last_name': 'Coscarza', 'phone': '+543584000005'},
    {'external_id': 'C-0089', 'first_name': 'Valeria', 'last_name': 'Gomez', 'phone': '+543584000006'},
    {'external_id': 'C-0092', 'first_name': 'Nelly', 'last_name': 'Martinez', 'phone': '+543584000007'},
    {'external_id': 'C-0101', 'first_name': 'Heliosa', 'last_name': 'Paz', 'phone': '+543584000008'},
    {'external_id': 'C-0118', 'first_name': 'Damian', 'last_name': 'Sosa', 'phone': '+543584000009'},
    {'external_id': 'C-0122', 'first_name': 'Micaela', 'last_name': 'Robles', 'phone': '+543584000010'},
    {'external_id': 'C-0134', 'first_name': 'Pedro', 'last_name': 'Jauregui', 'phone': '+543584000011'},
    {'external_id': 'C-0140', 'first_name': 'Pilar', 'last_name': 'Mendez', 'phone': '+543584000012'},
    {'external_id': 'C-0156', 'first_name': 'Natalia', 'last_name': 'Leal', 'phone': '+543584000013'},
    {'external_id': 'C-0168', 'first_name': 'Carlos', 'last_name': 'Ramirez', 'phone': '+543584000014'},
    {'external_id': 'C-0177', 'first_name': 'Nicolas', 'last_name': 'Fernandez', 'phone': '+543584000015'},
    {'external_id': 'C-0189', 'first_name': 'Alvaro', 'last_name': 'Marta', 'phone': '+543584000016'},
    {'external_id': 'C-0201', 'first_name': 'Cristian', 'last_name': 'Lopez', 'phone': '+543584000017'},
    {'external_id': 'C-0212', 'first_name': 'Natalia', 'last_name': 'Viglianco', 'phone': '+543584000018'},
    {'external_id': 'C-0225', 'first_name': 'Miraela', 'last_name': 'Vidal', 'phone': '+543584000019'},
    {'external_id': 'C-0237', 'first_name': 'Jose', 'last_name': 'Navarro', 'phone': '+543584000020'},
]


ALIASES = [
    ('C-0212', 'Naty'),
    ('C-0168', 'Cuco'),
    ('C-0177', 'Nico'),
    ('C-0140', 'Pilu'),
]


DEMO_BATCHES = [
    {
        'fecha': date(2026, 4, 18),
        'source_filenames': ['vales_2026-04-18.jpg'],
        'vales': [
            {'importe': 54731, 'cliente_codigo': 'C-0012', 'cliente_raw': 'Silvi Farias', 'detalle': '', 'confianza': 0.94},
            {'importe': 63868, 'cliente_codigo': 'C-0034', 'cliente_raw': 'Juan Cornavilla', 'detalle': '', 'confianza': 0.88},
            {'importe': 7560, 'cliente_codigo': None, 'cliente_raw': 'Valery', 'detalle': '', 'confianza': 0.95},
        ],
    },
    {
        'fecha': date(2026, 4, 19),
        'source_filenames': ['vales_2026-04-19.jpg'],
        'vales': [
            {'importe': 16944, 'cliente_codigo': None, 'cliente_raw': 'Heliosa', 'detalle': '', 'confianza': 0.62},
            {'importe': 8834, 'cliente_codigo': None, 'cliente_raw': 'Valery', 'detalle': '', 'confianza': 0.92},
            {'importe': 12430, 'cliente_codigo': 'C-0212', 'cliente_raw': 'Naty', 'detalle': '', 'confianza': 0.88},
        ],
    },
]


class Command(BaseCommand):
    help = 'Carga usuarios, clientes y lotes demo para probar TransformValesCarni en local.'

    def handle(self, *args, **options):
        created_users = 0
        created_clients = 0

        users_by_username = {}
        for payload in USERS:
            user, created = User.objects.get_or_create(username=payload['username'])
            user.first_name = payload['first_name']
            user.last_name = payload['last_name']
            user.is_active = True
            user.is_staff = payload['is_staff']
            user.is_superuser = payload['is_superuser']
            user.set_password(payload['password'])
            user.save()
            users_by_username[user.username] = user
            if created:
                created_users += 1

        clients_by_code = {}
        for payload in CLIENTS:
            client, created = AccountClient.objects.update_or_create(
                external_id=payload['external_id'],
                defaults={
                    'first_name': payload['first_name'],
                    'last_name': payload['last_name'],
                    'phone': payload['phone'],
                },
            )
            clients_by_code[client.external_id] = client
            if created:
                created_clients += 1

        aliases_created = 0
        for client_code, alias_value in ALIASES:
            client = clients_by_code[client_code]
            _alias, created = ensure_alias(client, alias_value, auto_detected=False)
            if created:
                aliases_created += 1

        batches_created = 0
        if not ValeImportBatch.objects.exists():
            for demo_batch in DEMO_BATCHES:
                vales_payload = []
                for item in demo_batch['vales']:
                    client = clients_by_code.get(item['cliente_codigo']) if item['cliente_codigo'] else None
                    vales_payload.append({
                        'importe': item['importe'],
                        'cliente_id': str(client.id) if client else None,
                        'cliente_raw': item['cliente_raw'],
                        'detalle': item['detalle'],
                        'confianza': item['confianza'],
                    })

                create_vale_batch(
                    user=users_by_username['monica'],
                    batch_date=demo_batch['fecha'],
                    vales_payload=vales_payload,
                    source_filenames=demo_batch['source_filenames'],
                )
                batches_created += 1

        self.stdout.write(self.style.SUCCESS('Seed local listo para TransformValesCarni.'))
        self.stdout.write(f'Usuarios creados: {created_users}')
        self.stdout.write(f'Clientes creados: {created_clients}')
        self.stdout.write(f'Alias nuevos: {aliases_created}')
        self.stdout.write(f'Lotes demo creados: {batches_created}')
        self.stdout.write('Credenciales: monica / carni2026  |  dario / vales123')
