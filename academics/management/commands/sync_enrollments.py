"""
Management command to sync StudentSubjectEnrollment records.

Ensures every active student has enrollment records for all auto_enroll
subjects in their current class. This fixes the "108%" score entry progress
bug caused by students having scores but no enrollment records.

Can run for all tenants or a specific one via --schema.
"""
import logging

from django.core.management.base import BaseCommand
from django.db.models import F
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync missing StudentSubjectEnrollment records for all active students'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema',
            type=str,
            help='Run for a specific tenant schema only',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        from schools.models import School

        dry_run = options['dry_run']
        schema = options.get('schema')
        prefix = '[DRY RUN] ' if dry_run else ''

        if schema:
            tenants = School.objects.filter(schema_name=schema)
            if not tenants.exists():
                self.stderr.write(self.style.ERROR(f'Tenant "{schema}" not found.'))
                return
        else:
            tenants = School.objects.exclude(schema_name='public')

        if not tenants.exists():
            self.stdout.write('No tenants found.')
            return

        total_created = 0

        for tenant in tenants:
            self.stdout.write(f'\nProcessing: {tenant.name} ({tenant.schema_name})')

            try:
                with schema_context(tenant.schema_name):
                    created = self._sync_tenant(dry_run, prefix)
                    total_created += created
            except Exception as e:
                logger.error(
                    "Enrollment sync failed for tenant %s: %s",
                    tenant.schema_name, e
                )
                self.stderr.write(
                    self.style.ERROR(f'  Error: {e}')
                )

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefix}Sync complete across {tenants.count()} tenant(s): '
                f'{total_created} enrollment(s) created'
            )
        )

    def _sync_tenant(self, dry_run, prefix):
        from academics.models import ClassSubject, StudentSubjectEnrollment
        from students.models import Student

        created_count = 0

        from academics.models import Class as AcademicClass

        # Get all active classes that have students
        classes_with_students = (
            AcademicClass.objects.filter(
                students__status='active',
            ).distinct()
        )

        for cls in classes_with_students:
            # Get auto-enroll subjects for this class
            class_subjects = list(
                ClassSubject.objects.filter(
                    class_assigned=cls,
                    auto_enroll=True,
                )
            )

            if not class_subjects:
                continue

            # Get active students in this class
            students = list(
                Student.objects.filter(
                    current_class=cls,
                    status='active',
                )
            )

            if not students:
                continue

            # Reactivate inactive enrollments
            inactive_to_reactivate = StudentSubjectEnrollment.objects.filter(
                student__in=students,
                class_subject__in=class_subjects,
                is_active=False,
            )
            reactivate_count = inactive_to_reactivate.count()
            if reactivate_count:
                self.stdout.write(
                    f'  {prefix}{cls.name}: reactivating {reactivate_count} inactive enrollment(s)'
                )
                if not dry_run:
                    inactive_to_reactivate.update(is_active=True)
                created_count += reactivate_count

            # Build truly missing enrollments (no record at all)
            all_existing = set(
                StudentSubjectEnrollment.objects.filter(
                    student__in=students,
                    class_subject__in=class_subjects,
                ).values_list('student_id', 'class_subject_id')
            )

            to_create = []
            for student in students:
                for cs in class_subjects:
                    if (student.id, cs.id) not in all_existing:
                        to_create.append(
                            StudentSubjectEnrollment(
                                student=student,
                                class_subject=cs,
                                is_active=True,
                            )
                        )

            if to_create:
                self.stdout.write(
                    f'  {prefix}{cls.name}: {len(to_create)} missing enrollment(s) '
                    f'({len(students)} students x {len(class_subjects)} subjects)'
                )
                if not dry_run:
                    StudentSubjectEnrollment.objects.bulk_create(
                        to_create, ignore_conflicts=True
                    )
                created_count += len(to_create)

        # Deactivate orphaned enrollments (student no longer in the class)
        orphaned = StudentSubjectEnrollment.objects.filter(
            is_active=True,
        ).exclude(
            student__current_class_id=F('class_subject__class_assigned_id'),
        )
        orphan_count = orphaned.count()
        if orphan_count:
            self.stdout.write(
                f'  {prefix}Deactivating {orphan_count} orphaned enrollment(s) '
                f'(students no longer in the class)'
            )
            if not dry_run:
                orphaned.update(is_active=False)

        if created_count == 0 and orphan_count == 0:
            self.stdout.write('  All enrollments up to date.')

        return created_count
