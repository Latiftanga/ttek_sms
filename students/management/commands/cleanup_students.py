"""
Management command to perform cleanup tasks for the students app.
- Mark expired guardian invitations as expired
- Update overdue exeat statuses
"""
import logging
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from students.models import GuardianInvitation, Exeat

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
        dry_run = options['dry_run']
        prefix = '[DRY RUN] ' if dry_run else ''

        # 1. Mark expired invitations
        expired_invitations = GuardianInvitation.objects.filter(
            status=GuardianInvitation.Status.PENDING,
            expires_at__lt=timezone.now()
        )
        expired_count = expired_invitations.count()

        if expired_count:
            self.stdout.write(
                f'{prefix}Found {expired_count} expired invitation(s)'
            )
            if not dry_run:
                expired_invitations.update(status=GuardianInvitation.Status.EXPIRED)
                self.stdout.write(
                    self.style.SUCCESS(f'Marked {expired_count} invitation(s) as expired')
                )
        else:
            self.stdout.write('No expired invitations found')

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
                f'{prefix}Found {overdue_count} overdue exeat(s)'
            )
            if not dry_run:
                self.stdout.write(
                    self.style.SUCCESS(f'Marked {overdue_count} exeat(s) as overdue')
                )
        else:
            self.stdout.write('No overdue exeats found')

        # Summary
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefix}Cleanup complete: '
                f'{expired_count} invitation(s), {overdue_count} exeat(s)'
            )
        )
