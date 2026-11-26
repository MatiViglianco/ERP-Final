from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from statsapp.arca_client import ArcaError
from statsapp.arca_retry import verify_invoices_with_arca


class Command(BaseCommand):
    help = 'Compara los comprobantes autorizados del mes contra ARCA (FECompConsultar).'

    def add_arguments(self, parser):
        today = timezone.localdate()
        parser.add_argument('--year', type=int, default=today.year)
        parser.add_argument('--month', type=int, default=today.month)

    def handle(self, *args, **options):
        start = date(options['year'], options['month'], 1)
        end = (date(start.year + (start.month == 12), start.month % 12 + 1, 1) - timedelta(days=1))
        try:
            report = verify_invoices_with_arca(start, end)
        except ArcaError as exc:
            raise CommandError(f'No se pudo verificar con ARCA: {exc}') from exc
        totals = report['totals']
        self.stdout.write(f"Periodo {start} a {end}: {report['checked']} comprobantes verificados")
        self.stdout.write(f"Resultados: {report['counts']}")
        self.stdout.write(
            f"Facturas ERP ${totals['erp_invoices']:,.2f} / ARCA ${totals['arca_invoices']:,.2f} | "
            f"NC ERP ${totals['erp_credit_notes']:,.2f} / ARCA ${totals['arca_credit_notes']:,.2f}"
        )
        for entry in report['problems']:
            self.stdout.write(f"  {entry['voucher']} ${entry['total']:,.2f}: {'; '.join(entry['problems'])}")
        for voucher in report['not_in_erp']['vouchers']:
            self.stdout.write(f"  En ARCA y no en el ERP: {voucher['voucher']} ${voucher['total']:,.2f} {voucher['issue_date']}")
        self.stdout.write(self.style.SUCCESS('Todo coincide') if report['all_ok'] else self.style.WARNING('Hay diferencias'))
