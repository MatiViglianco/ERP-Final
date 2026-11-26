from django.core.management.base import BaseCommand

from statsapp.arca_retry import retry_pending_invoices


class Command(BaseCommand):
    help = 'Reintenta las facturas que fallaron porque ARCA no respondio (si ARCA ya responde).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=200)

    def handle(self, *args, **options):
        summary = retry_pending_invoices(limit=options['limit'])
        self.stdout.write(
            f"candidatas={summary['candidates']} autorizadas={summary['authorized']} "
            f"fallidas={summary['failed']} pendientes={summary['still_pending']} "
            f"arca_up={summary['arca_up']} {summary['detail']}"
        )
