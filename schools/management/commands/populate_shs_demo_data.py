"""
Management command to populate an SHS with demo data.

Usage:
    python manage.py populate_shs_demo_data "Demo SHS"
    python manage.py populate_shs_demo_data "Demo SHS" --students-per-class 10
"""
from datetime import date, timedelta, time

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from schools.models import School
from academics.models import Programme, Class
from teachers.models import Teacher
from students.models import House, HouseMaster, Exeat, Student
from schools.management.commands._demo_helpers import (
    configure_school_settings,
    ensure_admin_user,
    create_academic_year,
    create_semesters,
    create_teachers,
    create_students_and_guardians,
    create_classrooms,
    create_class_subjects,
    create_assignments_and_scores,
    run_seed_commands,
)


# Deterministic teacher list for SHS
SHS_TEACHERS = [
    {
        'first_name': 'Kwadwo',
        'last_name': 'Appiah',
        'gender': 'M',
        'title': 'MR',

        'staff_id': 'ST001',
    },
    {
        'first_name': 'Adwoa',
        'last_name': 'Osei',
        'gender': 'F',
        'title': 'MRS',

        'staff_id': 'ST002',
    },
    {
        'first_name': 'Kweku',
        'last_name': 'Bonsu',
        'gender': 'M',
        'title': 'MR',

        'staff_id': 'ST003',
    },
    {
        'first_name': 'Afia',
        'last_name': 'Gyamfi',
        'gender': 'F',
        'title': 'MS',

        'staff_id': 'ST004',
    },
    {
        'first_name': 'Yaw',
        'last_name': 'Antwi',
        'gender': 'M',
        'title': 'MR',

        'staff_id': 'ST005',
    },
    {
        'first_name': 'Akosua',
        'last_name': 'Tetteh',
        'gender': 'F',
        'title': 'MRS',

        'staff_id': 'ST006',
    },
    {
        'first_name': 'Kojo',
        'last_name': 'Larbi',
        'gender': 'M',
        'title': 'MR',

        'staff_id': 'ST007',
    },
    {
        'first_name': 'Esi',
        'last_name': 'Addo',
        'gender': 'F',
        'title': 'MS',

        'staff_id': 'ST008',
    },
    {
        'first_name': 'Nana',
        'last_name': 'Ofori',
        'gender': 'M',
        'title': 'MR',

        'staff_id': 'ST009',
    },
    {
        'first_name': 'Abena',
        'last_name': 'Poku',
        'gender': 'F',
        'title': 'MRS',

        'staff_id': 'ST010',
    },
    {
        'first_name': 'Kwabena',
        'last_name': 'Kumi',
        'gender': 'M',
        'title': 'DR',

        'staff_id': 'ST011',
    },
    {
        'first_name': 'Yaa',
        'last_name': 'Afriyie',
        'gender': 'F',
        'title': 'MRS',

        'staff_id': 'ST012',
    },
]


class Command(BaseCommand):
    help = 'Populate an SHS tenant with demo data'

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
            f'with SHS demo data...\n'
        ))

        admin_email = 'admin@demoshs.com'
        admin_password = 'Demo@2026'

        with schema_context(schema):
            # 1. Admin user
            ensure_admin_user(admin_email, admin_password, self.stdout)

            # 2. Seed academic data
            run_seed_commands(schema, self.stdout)

            # 3. School settings
            configure_school_settings('semester', self.stdout)

            # 4. Academic year + 2 semesters
            academic_year = create_academic_year(self.stdout)
            create_semesters(academic_year, self.stdout)

            # 5. Houses
            houses = self._create_houses()

            # 6. Classes: 3 programmes x 3 years
            self._create_shs_classes()

            # 7. Teachers
            create_teachers(SHS_TEACHERS, schema, self.stdout)

            # 8. Students + guardians (with house assignment)
            create_students_and_guardians(
                students_per_class, houses=houses, stdout=self.stdout
            )

            # 9. Housemasters
            self._assign_housemasters(houses, academic_year)

            # 10. Form masters
            self._assign_form_masters()

            # 11. Exeats
            self._create_exeats(academic_year)

            # 12. Class-subject assignments, classrooms
            create_class_subjects(self.stdout)
            create_classrooms(self.stdout)

            # 13. Assignments + scores
            create_assignments_and_scores(self.stdout)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! SHS "{school.name}" populated successfully.'
        ))

    def _create_houses(self):
        """Create 4 houses for the SHS."""
        self.stdout.write('  Creating houses...')
        houses_data = [
            ('Blue House', 'Blue', '#3b82f6', 'Unity and Strength'),
            ('Red House', 'Red', '#ef4444', 'Courage and Determination'),
            ('Green House', 'Green', '#22c55e', 'Growth and Prosperity'),
            ('Yellow House', 'Yellow', '#eab308', 'Wisdom and Excellence'),
        ]
        houses = []
        for name, color, code, motto in houses_data:
            house, _ = House.objects.get_or_create(
                name=name,
                defaults={
                    'color': color,
                    'color_code': code,
                    'motto': motto,
                    'is_active': True,
                },
            )
            houses.append(house)
        self.stdout.write(f'    - {len(houses)} houses')
        return houses

    def _create_shs_classes(self):
        """Create SHS classes: 3 programmes x 3 year levels."""
        self.stdout.write('  Creating SHS classes...')
        programmes_to_use = [
            ('General Arts', 'ART'),
            ('General Science', 'SCI'),
            ('Business', 'BUS'),
        ]
        created = 0
        for prog_name, prog_code in programmes_to_use:
            programme = Programme.objects.filter(code=prog_code).first()
            if not programme:
                self.stdout.write(
                    f'    - Programme {prog_code} not found, skipping'
                )
                continue
            for year in range(1, 4):
                _, was_created = Class.objects.get_or_create(
                    level_type='shs',
                    level_number=year,
                    programme=programme,
                    section='',
                    defaults={'capacity': 40, 'is_active': True},
                )
                if was_created:
                    created += 1

        total = Class.objects.filter(is_active=True).count()
        self.stdout.write(f'    - {created} new classes (total {total})')

    def _assign_housemasters(self, houses, academic_year):
        """Assign 4 teachers as housemasters, 1 as senior housemaster."""
        self.stdout.write('  Assigning housemasters...')
        teachers = list(
            Teacher.objects.filter(status='active').order_by('staff_id')
        )
        if len(teachers) < 5:
            self.stdout.write('    - Not enough teachers for housemasters')
            return

        assigned = 0
        for i, house in enumerate(houses):
            teacher = teachers[i]
            _, was_created = HouseMaster.objects.get_or_create(
                house=house,
                academic_year=academic_year,
                defaults={
                    'teacher': teacher,
                    'is_senior': False,
                    'is_active': True,
                },
            )
            if was_created:
                assigned += 1
                self.stdout.write(
                    f'    - {teacher.full_name} -> {house.name}'
                )

        # Promote first housemaster to senior housemaster
        existing_senior = HouseMaster.objects.filter(
            academic_year=academic_year,
            is_senior=True,
            is_active=True,
        ).first()
        if not existing_senior:
            # Create a senior housemaster entry — assign to first house,
            # replace the existing one with is_senior=True
            first_hm = HouseMaster.objects.filter(
                house=houses[0],
                academic_year=academic_year,
                is_active=True,
            ).first()
            if first_hm:
                first_hm.is_senior = True
                first_hm.save(update_fields=['is_senior'])
                self.stdout.write(
                    f'    - {first_hm.teacher.full_name} '
                    f'promoted to Senior Housemaster'
                )
            else:
                self.stdout.write('    - Could not assign senior housemaster')
        self.stdout.write(f'    - {assigned} housemasters assigned')

    def _assign_form_masters(self):
        """Assign class teachers (form masters) to classes."""
        self.stdout.write('  Assigning form masters...')
        teachers = list(
            Teacher.objects.filter(status='active').order_by('staff_id')
        )
        classes = Class.objects.filter(is_active=True, class_teacher__isnull=True)

        assigned = 0
        for i, cls in enumerate(classes):
            if i < len(teachers):
                cls.class_teacher = teachers[i % len(teachers)]
                cls.save(update_fields=['class_teacher'])
                assigned += 1

        self.stdout.write(f'    - {assigned} form masters assigned')

    def _create_exeats(self, academic_year):
        """Create sample exeats in various statuses."""
        self.stdout.write('  Creating sample exeats...')
        students = list(
            Student.objects.filter(status='active').order_by('admission_number')[:8]
        )
        if len(students) < 6:
            self.stdout.write('    - Not enough students for exeats')
            return

        teachers = list(
            Teacher.objects.filter(status='active').order_by('staff_id')
        )
        housemaster = teachers[0] if teachers else None
        senior_hm = HouseMaster.objects.filter(
            academic_year=academic_year,
            is_senior=True,
            is_active=True,
        ).select_related('teacher').first()
        senior_teacher = senior_hm.teacher if senior_hm else housemaster

        today = date.today()
        now = timezone.now()

        exeats_data = [
            # 1. Approved internal
            {
                'student': students[0],
                'exeat_type': 'internal',
                'reason': 'Visit to the local clinic',
                'destination': 'Accra Polyclinic',
                'departure_date': today,
                'departure_time': time(9, 0),
                'expected_return_date': today,
                'expected_return_time': time(14, 0),
                'status': 'approved',
                'housemaster': housemaster,
                'approved_by': housemaster,
                'approved_at': now - timedelta(hours=2),
            },
            # 2. Completed external
            {
                'student': students[1],
                'exeat_type': 'external',
                'reason': 'Family funeral in Kumasi',
                'destination': 'Kumasi',
                'departure_date': today - timedelta(days=7),
                'departure_time': time(8, 0),
                'expected_return_date': today - timedelta(days=4),
                'expected_return_time': time(18, 0),
                'status': 'completed',
                'housemaster': housemaster,
                'recommended_by': housemaster,
                'recommended_at': now - timedelta(days=8),
                'approved_by': senior_teacher,
                'approved_at': now - timedelta(days=8),
                'actual_departure': now - timedelta(days=7),
                'actual_return': now - timedelta(days=4),
            },
            # 3. Pending external
            {
                'student': students[2],
                'exeat_type': 'external',
                'reason': 'Medical appointment in Tema',
                'destination': 'Tema General Hospital',
                'departure_date': today + timedelta(days=2),
                'departure_time': time(7, 0),
                'expected_return_date': today + timedelta(days=3),
                'expected_return_time': time(17, 0),
                'status': 'pending',
                'housemaster': housemaster,
            },
            # 4. Recommended (awaiting senior approval)
            {
                'student': students[3],
                'exeat_type': 'external',
                'reason': 'Visit home for family event',
                'destination': 'Cape Coast',
                'departure_date': today + timedelta(days=1),
                'departure_time': time(10, 0),
                'expected_return_date': today + timedelta(days=3),
                'expected_return_time': time(16, 0),
                'status': 'recommended',
                'housemaster': housemaster,
                'recommended_by': housemaster,
                'recommended_at': now - timedelta(hours=5),
            },
            # 5. Rejected external
            {
                'student': students[4],
                'exeat_type': 'external',
                'reason': 'Friend birthday party',
                'destination': 'Accra',
                'departure_date': today - timedelta(days=3),
                'departure_time': time(14, 0),
                'expected_return_date': today - timedelta(days=1),
                'expected_return_time': time(18, 0),
                'status': 'rejected',
                'housemaster': housemaster,
                'recommended_by': housemaster,
                'recommended_at': now - timedelta(days=4),
                'approved_by': senior_teacher,
                'approved_at': now - timedelta(days=4),
                'rejection_reason': 'Not a valid reason for exeat during '
                                    'exam period.',
            },
            # 6. Active (student currently out)
            {
                'student': students[5],
                'exeat_type': 'internal',
                'reason': 'Dentist appointment',
                'destination': 'Legon Dental Clinic',
                'departure_date': today,
                'departure_time': time(8, 30),
                'expected_return_date': today,
                'expected_return_time': time(13, 0),
                'status': 'active',
                'housemaster': housemaster,
                'approved_by': housemaster,
                'approved_at': now - timedelta(hours=3),
                'actual_departure': now - timedelta(hours=2),
            },
        ]

        created = 0
        for data in exeats_data:
            student = data.pop('student')
            # Check idempotency by student + departure_date + destination
            if Exeat.objects.filter(
                student=student,
                departure_date=data['departure_date'],
                destination=data['destination'],
            ).exists():
                continue

            Exeat.objects.create(student=student, **data)
            created += 1

        self.stdout.write(f'    - {created} exeats created')
