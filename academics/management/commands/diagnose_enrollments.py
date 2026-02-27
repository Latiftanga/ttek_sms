"""
Management command to diagnose enrollment issues for a specific class.
Shows students, ClassSubject auto_enroll flags, and enrollment counts.
"""
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Diagnose enrollment issues for a class in a tenant'

    def add_arguments(self, parser):
        parser.add_argument('--schema', type=str, required=True, help='Tenant schema name')
        parser.add_argument('--class-name', type=str, required=True, help='Class name (e.g. B5)')

    def handle(self, *args, **options):
        schema = options['schema']
        class_name = options['class_name']

        from schools.models import School
        if not School.objects.filter(schema_name=schema).exists():
            self.stderr.write(self.style.ERROR(f'Tenant "{schema}" not found.'))
            return

        with schema_context(schema):
            from academics.models import Class, ClassSubject, StudentSubjectEnrollment
            from students.models import Student

            cls = Class.objects.filter(name=class_name).first()
            if not cls:
                self.stderr.write(self.style.ERROR(f'Class "{class_name}" not found.'))
                return

            self.stdout.write(f'Class: {cls.name} (id={cls.id})')
            self.stdout.write('')

            # Students
            students = Student.objects.filter(current_class=cls)
            self.stdout.write(f'Students ({students.count()}):')
            for s in students:
                enroll_count = StudentSubjectEnrollment.objects.filter(
                    student=s, class_subject__class_assigned=cls, is_active=True
                ).count()
                self.stdout.write(
                    f'  {s.first_name} {s.last_name} (id={s.id}, status={s.status}, enrollments={enroll_count})'
                )

            self.stdout.write('')

            # ClassSubjects
            self.stdout.write('Subjects:')
            for cs in ClassSubject.objects.filter(class_assigned=cls).select_related('subject'):
                enrolled = StudentSubjectEnrollment.objects.filter(
                    class_subject=cs, is_active=True
                ).count()
                self.stdout.write(
                    f'  {cs.subject.short_name}: auto_enroll={cs.auto_enroll}, enrolled={enrolled}'
                )
