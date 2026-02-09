"""
Management command to populate a Basic school with demo data.

Usage:
    python manage.py populate_basic_demo_data "Demo Basic School"
    python manage.py populate_basic_demo_data "Demo Basic School" --students-per-class 10
"""
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from schools.models import School
from academics.models import Class
from schools.management.commands._demo_helpers import (
    configure_school_settings,
    ensure_admin_user,
    create_academic_year,
    create_terms,
    create_teachers,
    create_students_and_guardians,
    create_classrooms,
    create_class_subjects,
    create_assignments_and_scores,
    run_seed_commands,
)


# Deterministic teacher list for basic schools
BASIC_TEACHERS = [
    {
        'first_name': 'Kwame',
        'last_name': 'Asante',
        'gender': 'M',
        'title': 'MR',

        'staff_id': 'BT001',
    },
    {
        'first_name': 'Ama',
        'last_name': 'Mensah',
        'gender': 'F',
        'title': 'MRS',

        'staff_id': 'BT002',
    },
    {
        'first_name': 'Kofi',
        'last_name': 'Boateng',
        'gender': 'M',
        'title': 'MR',

        'staff_id': 'BT003',
    },
    {
        'first_name': 'Abena',
        'last_name': 'Owusu',
        'gender': 'F',
        'title': 'MS',

        'staff_id': 'BT004',
    },
    {
        'first_name': 'Yaw',
        'last_name': 'Frimpong',
        'gender': 'M',
        'title': 'MR',

        'staff_id': 'BT005',
    },
    {
        'first_name': 'Akua',
        'last_name': 'Darko',
        'gender': 'F',
        'title': 'MRS',

        'staff_id': 'BT006',
    },
    {
        'first_name': 'Kwesi',
        'last_name': 'Adjei',
        'gender': 'M',
        'title': 'MR',

        'staff_id': 'BT007',
    },
    {
        'first_name': 'Efua',
        'last_name': 'Quartey',
        'gender': 'F',
        'title': 'MS',

        'staff_id': 'BT008',
    },
]


class Command(BaseCommand):
    help = 'Populate a Basic school tenant with demo data'

    def add_arguments(self, parser):
        parser.add_argument(
            'school_name',
            type=str,
            help='Name of the school to populate (must already exist)',
        )
        parser.add_argument(
            '--students-per-class',
            type=int,
            default=7,
            help='Number of students per class (default: 7)',
        )

    def handle(self, *args, **options):
        school_name = options['school_name']
        students_per_class = options['students_per_class']

        # Look up school
        try:
            school = School.objects.get(name=school_name)
        except School.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                f"School '{school_name}' not found. "
                f"Create it first with: python manage.py create_school"
            ))
            return

        schema = school.schema_name
        self.stdout.write(self.style.NOTICE(
            f'\nPopulating "{school.name}" (schema: {schema}) '
            f'with basic school demo data...\n'
        ))

        admin_email = 'admin@demobasic.com'
        admin_password = 'Demo@2026'

        with schema_context(schema):
            # 1. Admin user
            ensure_admin_user(admin_email, admin_password, self.stdout)

            # 2. Seed academic data
            run_seed_commands(schema, self.stdout)

            # 3. School settings
            configure_school_settings('term', self.stdout)

            # 4. Academic year + 3 terms
            academic_year = create_academic_year(self.stdout)
            create_terms(academic_year, self.stdout)

            # 5. Classes: KG 1-2, B1-B9
            self._create_basic_classes()

            # 6. Teachers
            create_teachers(BASIC_TEACHERS, schema, self.stdout)

            # 7. Students + guardians (no houses)
            create_students_and_guardians(
                students_per_class, houses=[], stdout=self.stdout
            )

            # 8. Class-subject assignments, classrooms
            create_class_subjects(self.stdout)
            create_classrooms(self.stdout)

            # 9. Assignments + scores
            create_assignments_and_scores(self.stdout)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! Basic school "{school.name}" populated successfully.'
        ))

    def _create_basic_classes(self):
        """Create KG 1-2 and B1-B9 classes."""
        self.stdout.write('  Creating classes...')
        created = 0

        # KG 1 & 2
        for level_num in range(1, 3):
            _, was_created = Class.objects.get_or_create(
                level_type='kg',
                level_number=level_num,
                section='',
                defaults={'capacity': 30, 'is_active': True},
            )
            if was_created:
                created += 1

        # B1 - B9
        for level_num in range(1, 10):
            _, was_created = Class.objects.get_or_create(
                level_type='basic',
                level_number=level_num,
                section='',
                defaults={'capacity': 35, 'is_active': True},
            )
            if was_created:
                created += 1

        total = Class.objects.filter(is_active=True).count()
        self.stdout.write(
            f'    - {created} new classes (total {total})'
        )
