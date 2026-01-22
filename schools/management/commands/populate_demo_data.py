"""
Management command to populate demo schools with dummy data.
Run this after create_demo_schools.
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context

from schools.models import School
from core.models import AcademicYear, Term, SchoolSettings
from academics.models import (
    Programme, Class, Subject, ClassSubject, Period, Classroom
)
from teachers.models import Teacher
from students.models import House, Guardian, Student, StudentGuardian, Enrollment
from accounts.models import User
from gradebook.models import (
    GradingSystem, GradeScale, AssessmentCategory, Assignment, Score
)


# Ghanaian names for realistic data
MALE_FIRST_NAMES = [
    'Kwame', 'Kofi', 'Kweku', 'Yaw', 'Kwabena', 'Kojo', 'Kwasi',
    'Nana', 'Owusu', 'Mensah', 'Ato', 'Fiifi', 'Papa', 'Nii',
    'Edem', 'Selorm', 'Dela', 'Senyo', 'Kodzo', 'Komla',
    'Abdul', 'Mohammed', 'Ibrahim', 'Yusuf', 'Rashid',
    'Daniel', 'Samuel', 'Emmanuel', 'David', 'Michael',
]

FEMALE_FIRST_NAMES = [
    'Ama', 'Akua', 'Afia', 'Yaa', 'Abena', 'Adwoa', 'Akosua',
    'Efua', 'Esi', 'Araba', 'Ekua', 'Adjoa', 'Afua', 'Akos',
    'Dzifa', 'Elikem', 'Sena', 'Enyonam', 'Kafui', 'Sedinam',
    'Fatima', 'Aisha', 'Zainab', 'Amina', 'Halima',
    'Grace', 'Sarah', 'Mary', 'Elizabeth', 'Rebecca',
]

LAST_NAMES = [
    'Mensah', 'Asante', 'Owusu', 'Boateng', 'Agyei', 'Amoah', 'Appiah',
    'Osei', 'Bonsu', 'Frimpong', 'Darko', 'Kyei', 'Antwi', 'Opoku',
    'Adjei', 'Quartey', 'Tetteh', 'Quaye', 'Nartey', 'Laryea',
    'Addo', 'Afriyie', 'Asamoah', 'Badu', 'Danquah', 'Eshun',
    'Gyamfi', 'Hammond', 'Inkoom', 'Jnr', 'Kumi', 'Larbi',
    'Mohammed', 'Nuamah', 'Ofori', 'Poku', 'Quansah', 'Rockson',
]

OCCUPATIONS = [
    'Teacher', 'Trader', 'Farmer', 'Nurse', 'Engineer', 'Doctor',
    'Accountant', 'Driver', 'Police Officer', 'Banker', 'Lawyer',
    'Civil Servant', 'Business Owner', 'Mechanic', 'Electrician',
]


class Command(BaseCommand):
    help = 'Populate demo school with dummy data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema',
            type=str,
            required=True,
            help='Schema name of the demo school (demo_basic or demo_shs)',
        )
        parser.add_argument(
            '--students-per-class',
            type=int,
            default=25,
            help='Number of students per class (default: 25)',
        )

    def handle(self, *args, **options):
        schema_name = options['schema']
        students_per_class = options['students_per_class']

        # Verify school exists
        try:
            school = School.objects.get(schema_name=schema_name)
        except School.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"School with schema '{schema_name}' not found."))
            self.stderr.write("Run 'python manage.py create_demo_schools' first.")
            return

        self.stdout.write(self.style.NOTICE(f'\nPopulating {school.name} with demo data...'))

        with schema_context(schema_name):
            self._populate_school_settings(school)
            self._create_academic_year_and_terms()

            if school.education_system == 'shs':
                self._create_programmes()

            self._create_houses()
            self._create_teachers(school)
            self._create_classes(school)
            self._create_subjects(school)
            self._create_class_subjects()
            self._create_periods()
            self._create_classrooms()
            self._create_grading_system(school)
            self._create_assessment_categories()
            self._create_students_and_guardians(students_per_class)
            self._create_assignments_and_scores()

        self.stdout.write(self.style.SUCCESS(f'\n✓ Demo data populated for {school.name}!'))

    def _populate_school_settings(self, school):
        self.stdout.write('  Creating school settings...')
        settings = SchoolSettings.load()
        settings.display_name = school.name
        settings.motto = "Excellence Through Knowledge" if school.education_system == 'basic' else "Aspire to Achieve"
        settings.education_system = school.education_system
        settings.academic_period_type = 'term'
        settings.primary_color = '#1e40af' if school.education_system == 'basic' else '#166534'
        settings.secondary_color = '#3b82f6' if school.education_system == 'basic' else '#22c55e'
        settings.setup_completed = True
        settings.save()
        self.stdout.write('    ✓ School settings configured')

    def _create_academic_year_and_terms(self):
        self.stdout.write('  Creating academic year and terms...')

        # Create current academic year
        today = date.today()
        year_start = date(today.year if today.month >= 9 else today.year - 1, 9, 1)
        year_end = date(year_start.year + 1, 7, 31)

        academic_year, created = AcademicYear.objects.get_or_create(
            name=f"{year_start.year}/{year_end.year}",
            defaults={
                'start_date': year_start,
                'end_date': year_end,
                'is_current': True,
            }
        )

        # Create terms
        terms_data = [
            ('First Term', 1, year_start, year_start + timedelta(days=90)),
            ('Second Term', 2, year_start + timedelta(days=100), year_start + timedelta(days=190)),
            ('Third Term', 3, year_start + timedelta(days=200), year_end),
        ]

        for name, number, start, end in terms_data:
            term, _ = Term.objects.get_or_create(
                academic_year=academic_year,
                term_number=number,
                defaults={
                    'name': name,
                    'start_date': start,
                    'end_date': end,
                    'is_current': (number == 1),
                }
            )

        self.stdout.write(f'    ✓ Academic year: {academic_year.name}')

    def _create_programmes(self):
        self.stdout.write('  Creating SHS programmes...')
        programmes = [
            ('General Arts', 'ART', 'Arts subjects including History, Government, Literature'),
            ('General Science', 'SCI', 'Science subjects including Physics, Chemistry, Biology'),
            ('Business', 'BUS', 'Business subjects including Accounting, Economics'),
            ('Visual Arts', 'VIS', 'Visual arts including Graphic Design, Sculpture'),
            ('Home Economics', 'HOM', 'Home economics and related subjects'),
            ('Agricultural Science', 'AGR', 'Agricultural science and related subjects'),
        ]
        for name, code, desc in programmes:
            Programme.objects.get_or_create(
                code=code,
                defaults={'name': name, 'description': desc, 'is_active': True}
            )
        self.stdout.write(f'    ✓ Created {len(programmes)} programmes')

    def _create_houses(self):
        self.stdout.write('  Creating houses...')
        houses = [
            ('Blue House', 'Blue', '#3b82f6', 'Unity and Strength'),
            ('Red House', 'Red', '#ef4444', 'Courage and Determination'),
            ('Green House', 'Green', '#22c55e', 'Growth and Prosperity'),
            ('Yellow House', 'Yellow', '#eab308', 'Wisdom and Excellence'),
        ]
        for name, color, code, motto in houses:
            House.objects.get_or_create(
                name=name,
                defaults={'color': color, 'color_code': code, 'motto': motto, 'is_active': True}
            )
        self.stdout.write(f'    ✓ Created {len(houses)} houses')

    def _create_teachers(self, school):
        self.stdout.write('  Creating teachers...')

        # Number of teachers based on school type
        num_teachers = 15 if school.education_system == 'basic' else 25
        titles = ['Mr.', 'Mrs.', 'Miss', 'Mr.', 'Mrs.']  # Weighted towards Mr/Mrs

        for i in range(num_teachers):
            gender = random.choice(['M', 'F'])
            title = random.choice(['Mr.', 'Mr.'] if gender == 'M' else ['Mrs.', 'Miss'])
            first_name = random.choice(MALE_FIRST_NAMES if gender == 'M' else FEMALE_FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)

            email = f"{first_name.lower()}.{last_name.lower()}{i}@{school.schema_name}.edu.gh"

            # Create user for teacher
            user = User.objects.create_user(
                email=email,
                password='Teacher@2024',
                first_name=first_name,
                last_name=last_name,
                is_teacher=True,
            )

            # Create teacher profile
            Teacher.objects.create(
                user=user,
                title=title,
                first_name=first_name,
                last_name=last_name,
                gender=gender,
                staff_id=f"TCH{str(i+1).zfill(4)}",
                phone_number=f"+23324{random.randint(1000000, 9999999)}",
                email=email,
                employment_date=date.today() - timedelta(days=random.randint(365, 3650)),
                status='active',
            )

        self.stdout.write(f'    ✓ Created {num_teachers} teachers')

    def _create_classes(self, school):
        self.stdout.write('  Creating classes...')
        teachers = list(Teacher.objects.filter(status='active'))
        teacher_idx = 0

        if school.education_system == 'basic':
            # Basic school classes
            levels = [
                ('creche', 1, 1),
                ('nursery', 1, 2),
                ('kg', 1, 2),
                ('primary', 1, 6),
                ('jhs', 1, 3),
            ]
            for level_type, start, end in levels:
                for level_num in range(start, end + 1):
                    for section in ['A']:  # Single stream for demo
                        Class.objects.get_or_create(
                            level_type=level_type,
                            level_number=level_num,
                            section=section,
                            defaults={
                                'class_teacher': teachers[teacher_idx % len(teachers)] if teachers else None,
                                'capacity': 35,
                                'is_active': True,
                            }
                        )
                        teacher_idx += 1
        else:
            # SHS classes
            programmes = list(Programme.objects.all())
            for programme in programmes[:4]:  # Use 4 main programmes
                for year in range(1, 4):  # SHS 1, 2, 3
                    Class.objects.get_or_create(
                        level_type='shs',
                        level_number=year,
                        section='A',
                        programme=programme,
                        defaults={
                            'class_teacher': teachers[teacher_idx % len(teachers)] if teachers else None,
                            'capacity': 40,
                            'is_active': True,
                        }
                    )
                    teacher_idx += 1

        class_count = Class.objects.count()
        self.stdout.write(f'    ✓ Created {class_count} classes')

    def _create_subjects(self, school):
        self.stdout.write('  Creating subjects...')

        if school.education_system == 'basic':
            subjects = [
                ('English Language', 'ENG', True),
                ('Mathematics', 'MATH', True),
                ('Integrated Science', 'SCI', True),
                ('Social Studies', 'SOC', True),
                ('Information Technology', 'ICT', True),
                ('Religious and Moral Education', 'RME', True),
                ('Creative Arts', 'ART', True),
                ('Ghanaian Language', 'GHL', False),
                ('French', 'FRE', False),
                ('Physical Education', 'PE', False),
            ]
        else:
            subjects = [
                # Core subjects
                ('Core Mathematics', 'CMATH', True),
                ('Core English', 'CENG', True),
                ('Integrated Science', 'CSCI', True),
                ('Social Studies', 'CSOC', True),
                # Electives
                ('Elective Mathematics', 'EMATH', False),
                ('Physics', 'PHY', False),
                ('Chemistry', 'CHEM', False),
                ('Biology', 'BIO', False),
                ('Economics', 'ECON', False),
                ('Business Management', 'BUS', False),
                ('Accounting', 'ACC', False),
                ('Government', 'GOV', False),
                ('History', 'HIST', False),
                ('Literature', 'LIT', False),
                ('Geography', 'GEO', False),
                ('French', 'FRE', False),
            ]

        for name, code, is_core in subjects:
            Subject.objects.get_or_create(
                short_name=code,
                defaults={'name': name, 'is_core': is_core, 'is_active': True}
            )

        self.stdout.write(f'    ✓ Created {len(subjects)} subjects')

    def _create_class_subjects(self):
        self.stdout.write('  Assigning subjects to classes...')

        teachers = list(Teacher.objects.filter(status='active'))
        classes = Class.objects.filter(is_active=True)
        core_subjects = Subject.objects.filter(is_core=True, is_active=True)
        elective_subjects = Subject.objects.filter(is_core=False, is_active=True)

        count = 0
        for cls in classes:
            # Assign all core subjects
            for subject in core_subjects:
                ClassSubject.objects.get_or_create(
                    class_assigned=cls,
                    subject=subject,
                    defaults={
                        'teacher': random.choice(teachers) if teachers else None,
                        'periods_per_week': random.randint(3, 5),
                    }
                )
                count += 1

            # Assign some elective subjects
            for subject in random.sample(list(elective_subjects), min(3, len(elective_subjects))):
                ClassSubject.objects.get_or_create(
                    class_assigned=cls,
                    subject=subject,
                    defaults={
                        'teacher': random.choice(teachers) if teachers else None,
                        'periods_per_week': random.randint(2, 4),
                    }
                )
                count += 1

        self.stdout.write(f'    ✓ Created {count} class-subject assignments')

    def _create_periods(self):
        self.stdout.write('  Creating timetable periods...')

        periods = [
            ('Assembly', '07:30', '08:00', 1, True),
            ('Period 1', '08:00', '08:40', 2, False),
            ('Period 2', '08:40', '09:20', 3, False),
            ('Period 3', '09:20', '10:00', 4, False),
            ('Break', '10:00', '10:30', 5, True),
            ('Period 4', '10:30', '11:10', 6, False),
            ('Period 5', '11:10', '11:50', 7, False),
            ('Period 6', '11:50', '12:30', 8, False),
            ('Lunch', '12:30', '13:30', 9, True),
            ('Period 7', '13:30', '14:10', 10, False),
            ('Period 8', '14:10', '14:50', 11, False),
        ]

        for name, start, end, order, is_break in periods:
            Period.objects.get_or_create(
                name=name,
                defaults={
                    'start_time': start,
                    'end_time': end,
                    'order': order,
                    'is_break': is_break,
                }
            )

        self.stdout.write(f'    ✓ Created {len(periods)} periods')

    def _create_classrooms(self):
        self.stdout.write('  Creating classrooms...')

        rooms = [
            ('Room 101', 'R101', 40, 'regular'),
            ('Room 102', 'R102', 40, 'regular'),
            ('Room 103', 'R103', 40, 'regular'),
            ('Room 104', 'R104', 40, 'regular'),
            ('Room 105', 'R105', 40, 'regular'),
            ('Science Lab', 'LAB1', 30, 'lab'),
            ('Computer Lab', 'COMP', 35, 'computer'),
            ('Library', 'LIB', 50, 'library'),
            ('Assembly Hall', 'HALL', 200, 'hall'),
        ]

        for name, code, capacity, room_type in rooms:
            Classroom.objects.get_or_create(
                name=name,
                defaults={
                    'code': code,
                    'capacity': capacity,
                    'room_type': room_type,
                    'is_active': True,
                }
            )

        self.stdout.write(f'    ✓ Created {len(rooms)} classrooms')

    def _create_grading_system(self, school):
        self.stdout.write('  Creating grading system...')

        if school.education_system == 'basic':
            system, _ = GradingSystem.objects.get_or_create(
                name='BECE Standard',
                level='BASIC',
                defaults={
                    'description': 'Ghana BECE grading system',
                    'pass_mark': Decimal('40.00'),
                    'credit_mark': Decimal('50.00'),
                }
            )
            grades = [
                ('1', 80, 100, 1, 'Excellent'),
                ('2', 70, 79, 2, 'Very Good'),
                ('3', 60, 69, 3, 'Good'),
                ('4', 55, 59, 4, 'Credit'),
                ('5', 50, 54, 5, 'Credit'),
                ('6', 45, 49, 6, 'Pass'),
                ('7', 40, 44, 7, 'Pass'),
                ('8', 35, 39, 8, 'Weak'),
                ('9', 0, 34, 9, 'Fail'),
            ]
        else:
            system, _ = GradingSystem.objects.get_or_create(
                name='WASSCE Standard',
                level='SHS',
                defaults={
                    'description': 'Ghana WASSCE grading system',
                    'pass_mark': Decimal('40.00'),
                    'credit_mark': Decimal('50.00'),
                }
            )
            grades = [
                ('A1', 80, 100, 1, 'Excellent'),
                ('B2', 70, 79, 2, 'Very Good'),
                ('B3', 65, 69, 3, 'Good'),
                ('C4', 60, 64, 4, 'Credit'),
                ('C5', 55, 59, 5, 'Credit'),
                ('C6', 50, 54, 6, 'Credit'),
                ('D7', 45, 49, 7, 'Pass'),
                ('E8', 40, 44, 8, 'Pass'),
                ('F9', 0, 39, 9, 'Fail'),
            ]

        for label, min_p, max_p, points, interp in grades:
            GradeScale.objects.get_or_create(
                grading_system=system,
                grade_label=label,
                defaults={
                    'min_percentage': Decimal(str(min_p)),
                    'max_percentage': Decimal(str(max_p)),
                    'aggregate_points': points,
                    'interpretation': interp,
                    'is_pass': points <= 8,
                    'is_credit': points <= 6,
                    'order': points,
                }
            )

        self.stdout.write(f'    ✓ Created grading system: {system.name}')

    def _create_assessment_categories(self):
        self.stdout.write('  Creating assessment categories...')

        categories = [
            ('Class Score', 'CA', 'CLASS_SCORE', 30, 1),
            ('Examination', 'EXAM', 'EXAM', 70, 2),
        ]

        for name, short, cat_type, percentage, order in categories:
            AssessmentCategory.objects.get_or_create(
                short_name=short,
                defaults={
                    'name': name,
                    'category_type': cat_type,
                    'percentage': percentage,
                    'order': order,
                    'is_active': True,
                }
            )

        self.stdout.write(f'    ✓ Created {len(categories)} assessment categories')

    def _create_students_and_guardians(self, students_per_class):
        self.stdout.write('  Creating students and guardians...')

        classes = Class.objects.filter(is_active=True)
        houses = list(House.objects.filter(is_active=True))
        academic_year = AcademicYear.objects.filter(is_current=True).first()

        student_count = 0
        guardian_count = 0

        for cls in classes:
            for i in range(students_per_class):
                gender = random.choice(['M', 'F'])
                first_name = random.choice(MALE_FIRST_NAMES if gender == 'M' else FEMALE_FIRST_NAMES)
                last_name = random.choice(LAST_NAMES)

                # Create student
                admission_num = f"STU{cls.pk:02d}{str(i+1).zfill(3)}"

                student = Student.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    gender=gender,
                    date_of_birth=date.today() - timedelta(days=random.randint(2000, 6000)),
                    admission_number=admission_num,
                    admission_date=date.today() - timedelta(days=random.randint(30, 365)),
                    current_class=cls,
                    house=random.choice(houses) if houses else None,
                    status='active',
                )
                student_count += 1

                # Create enrollment
                if academic_year:
                    Enrollment.objects.create(
                        student=student,
                        academic_year=academic_year,
                        class_assigned=cls,
                        status='active',
                    )

                # Create guardian(s)
                for j in range(random.randint(1, 2)):
                    guardian_gender = random.choice(['M', 'F'])
                    guardian_first = random.choice(MALE_FIRST_NAMES if guardian_gender == 'M' else FEMALE_FIRST_NAMES)
                    guardian_last = last_name  # Same family name

                    phone = f"+23320{random.randint(1000000, 9999999)}"

                    guardian, created = Guardian.objects.get_or_create(
                        phone_number=phone,
                        defaults={
                            'full_name': f"{guardian_first} {guardian_last}",
                            'email': f"{guardian_first.lower()}.{guardian_last.lower()}{random.randint(1,999)}@email.com",
                            'occupation': random.choice(OCCUPATIONS),
                            'address': f"{random.randint(1, 100)} {random.choice(LAST_NAMES)} Street, Accra",
                        }
                    )
                    if created:
                        guardian_count += 1

                    # Link guardian to student
                    relationship = 'father' if guardian_gender == 'M' else 'mother'
                    StudentGuardian.objects.get_or_create(
                        student=student,
                        guardian=guardian,
                        defaults={
                            'relationship': relationship,
                            'is_primary': (j == 0),
                            'is_emergency_contact': True,
                        }
                    )

        self.stdout.write(f'    ✓ Created {student_count} students')
        self.stdout.write(f'    ✓ Created {guardian_count} guardians')

    def _create_assignments_and_scores(self):
        self.stdout.write('  Creating assignments and scores...')

        term = Term.objects.filter(is_current=True).first()
        if not term:
            self.stdout.write('    ⚠ No current term found, skipping assignments')
            return

        categories = AssessmentCategory.objects.filter(is_active=True)
        class_subjects = ClassSubject.objects.select_related('class_assigned', 'subject')

        assignment_count = 0
        score_count = 0

        for cs in class_subjects:
            students = Student.objects.filter(
                current_class=cs.class_assigned,
                status='active'
            )

            for category in categories:
                # Create 2-3 assignments per category
                num_assignments = 2 if category.category_type == 'EXAM' else 3

                for i in range(num_assignments):
                    name = f"{category.short_name} {i+1}"
                    points = 100 if category.category_type == 'EXAM' else random.choice([20, 25, 30])

                    assignment, created = Assignment.objects.get_or_create(
                        assessment_category=category,
                        subject=cs.subject,
                        term=term,
                        name=name,
                        defaults={
                            'points_possible': Decimal(str(points)),
                            'date': date.today() - timedelta(days=random.randint(1, 60)),
                        }
                    )
                    if created:
                        assignment_count += 1

                    # Create scores for students
                    for student in students:
                        # Generate realistic score (normal distribution around 65%)
                        base_score = random.gauss(65, 15)
                        score_value = max(0, min(100, base_score)) * points / 100

                        Score.objects.get_or_create(
                            student=student,
                            assignment=assignment,
                            defaults={'points': Decimal(str(round(score_value, 2)))}
                        )
                        score_count += 1

        self.stdout.write(f'    ✓ Created {assignment_count} assignments')
        self.stdout.write(f'    ✓ Created {score_count} scores')
