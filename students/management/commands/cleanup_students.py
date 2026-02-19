"""
Management command to perform cleanup tasks for the students app.
- Mark expired guardian invitations as expired
- Update overdue exeat statuses

Must iterate over all tenants since this is a multi-tenant app.
"""
import logging
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cleanup expired invitations and update overdue exeat statuses'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        from schools.models import School

        dry_run = options['dry_run']
        prefix = '[DRY RUN] ' if dry_run else ''

        tenants = School.objects.exclude(schema_name='public')
        if not tenants.exists():
            self.stdout.write('No tenants found.')
            return

        total_expired = 0
        total_overdue = 0

        for tenant in tenants:
            self.stdout.write(f'\nProcessing tenant: {tenant.name} ({tenant.schema_name})')

            try:
                with schema_context(tenant.schema_name):
                    from students.models import GuardianInvitation, Exeat

                    # 1. Mark expired invitations
                    expired_invitations = GuardianInvitation.objects.filter(
                        status=GuardianInvitation.Status.PENDING,
                        expires_at__lt=timezone.now()
                    )
                    expired_count = expired_invitations.count()

                    if expired_count:
                        self.stdout.write(
                            f'  {prefix}Found {expired_count} expired invitation(s)'
                        )
                        if not dry_run:
                            expired_invitations.update(
                                status=GuardianInvitation.Status.EXPIRED
                            )

                    # 2. Update overdue exeats
                    now = timezone.now()
                    active_exeats = Exeat.objects.filter(
                        status__in=[Exeat.Status.ACTIVE, Exeat.Status.APPROVED]
                    )

                    overdue_count = 0
                    for exeat in active_exeats:
                        expected = datetime.combine(
                            exeat.expected_return_date,
                            exeat.expected_return_time
                        )
                        if timezone.is_naive(expected):
                            expected = timezone.make_aware(expected)

                        if now > expected:
                            overdue_count += 1
                            if not dry_run:
                                exeat.status = Exeat.Status.OVERDUE
                                exeat.save(update_fields=['status', 'updated_at'])

                    if overdue_count:
                        self.stdout.write(
                            f'  {prefix}Found {overdue_count} overdue exeat(s)'
                        )

                    total_expired += expired_count
                    total_overdue += overdue_count

            except Exception as e:
                logger.error(
                    "Cleanup failed for tenant %s: %s",
                    tenant.schema_name, e
                )
                self.stderr.write(
                    self.style.ERROR(
                        f'  Error processing {tenant.schema_name}: {e}'
                    )
                )

        # Summary
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefix}Cleanup complete across {tenants.count()} tenant(s): '
                f'{total_expired} invitation(s), {total_overdue} exeat(s)'
            )
        )
