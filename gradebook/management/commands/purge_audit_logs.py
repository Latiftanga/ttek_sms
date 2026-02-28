"""
Management command to purge old ScoreAuditLog entries.

Usage:
    # Purge logs older than 6 months (default) for a specific tenant
    python manage.py tenant_command purge_audit_logs --schema=demo

    # Purge logs older than 1 year
    python manage.py tenant_command purge_audit_logs --schema=demo --months=12

    # Dry run to see how many would be deleted
    python manage.py tenant_command purge_audit_logs --schema=demo --dry-run
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Purge ScoreAuditLog entries older than N months'

    def add_arguments(self, parser):
        parser.add_argument(
            '--months', type=int, default=6,
            help='Delete logs older than this many months (default: 6)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show count without deleting',
        )

    def handle(self, *args, **options):
        from gradebook.models import ScoreAuditLog

        months = options['months']
        cutoff = timezone.now() - timedelta(days=months * 30)
        qs = ScoreAuditLog.objects.filter(created_at__lt=cutoff)
        count = qs.count()

        if options['dry_run']:
            self.stdout.write(f'Would delete {count} audit log(s) older than {months} months.')
            return

        if count == 0:
            self.stdout.write(self.style.SUCCESS('No old audit logs to purge.'))
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Purged {deleted} audit log(s) older than {months} months (before {cutoff:%Y-%m-%d}).'
        ))
