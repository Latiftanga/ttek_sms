"""Remove orphaned SubjectTermGrade records for subjects no longer assigned to a class."""
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from academics.models import Class, ClassSubject, Subject
from gradebook.models import SubjectTermGrade, TermReport
from students.models import Student


class Command(BaseCommand):
    help = 'Clean up orphaned SubjectTermGrade records for a removed class subject'

    def add_arguments(self, parser):
        parser.add_argument('--schema', required=True, help='Tenant schema name')
        parser.add_argument('--class-name', required=True, help='Class name (e.g. B1)')
        parser.add_argument('--subject', required=True, help='Subject name or partial match')
        parser.add_argument('--dry-run', action='store_true', help='Preview without deleting')

    def handle(self, *args, **options):
        schema = options['schema']
        class_name = options['class_name']
        subject_query = options['subject']
        dry_run = options['dry_run']

        with schema_context(schema):
            class_obj = Class.objects.filter(name=class_name).first()
            if not class_obj:
                self.stderr.write(f'Class "{class_name}" not found.')
                return

            subject = Subject.objects.filter(name__icontains=subject_query).first()
            if not subject:
                self.stderr.write(f'No subject matching "{subject_query}".')
                return

            self.stdout.write(f'Class: {class_obj.name}')
            self.stdout.write(f'Subject: {subject.name}')

            cs_exists = ClassSubject.objects.filter(
                class_assigned=class_obj, subject=subject
            ).exists()
            self.stdout.write(f'ClassSubject still assigned: {cs_exists}')

            if cs_exists:
                self.stderr.write('ClassSubject still exists — nothing to clean up.')
                return

            student_ids = list(Student.objects.filter(
                current_class=class_obj, status='active'
            ).values_list('id', flat=True))

            orphaned = SubjectTermGrade.objects.filter(
                student_id__in=student_ids, subject=subject
            ).select_related('student')

            count = orphaned.count()
            self.stdout.write(f'Orphaned grades found: {count}')

            for g in orphaned:
                self.stdout.write(f'  {g.student.full_name}: {g.total_score} ({g.grade})')

            if count == 0:
                self.stdout.write('Nothing to clean up.')
                return

            if dry_run:
                self.stdout.write(self.style.WARNING('Dry run — no changes made.'))
                return

            orphaned.delete()
            self.stdout.write(self.style.SUCCESS(f'Deleted {count} orphaned grade(s).'))

            updated = 0
            for tr in TermReport.objects.filter(student_id__in=student_ids):
                tr.calculate_aggregates()
                tr.save()
                updated += 1

            self.stdout.write(self.style.SUCCESS(f'Recalculated {updated} term report(s).'))
