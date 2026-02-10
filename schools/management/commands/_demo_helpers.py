"""
Shared helper functions for demo data population commands.
Used by populate_basic_demo_data and populate_shs_demo_data.
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command

from core.models import AcademicYear, Term, SchoolSettings
from academics.models import (
    Class, Subject, ClassSubject, Classroom,
)
from teachers.models import Teacher
from students.models import (
    Guardian, Student, StudentGuardian, Enrollment,
)
from accounts.models import User
from gradebook.models import AssessmentCategory, Assignment, Score


# ---------------------------------------------------------------------------
# Ghanaian name data
# ---------------------------------------------------------------------------
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
    'Gyamfi', 'Hammond', 'Inkoom', 'Kumi', 'Larbi',
    'Nuamah', 'Ofori', 'Poku', 'Quansah', 'Rockson',
]

OCCUPATIONS = [
    'Teacher', 'Trader', 'Farmer', 'Nurse', 'Engineer', 'Doctor',
    'Accountant', 'Driver', 'Police Officer', 'Banker', 'Lawyer',
    'Civil Servant', 'Business Owner', 'Mechanic', 'Electrician',
]


# ---------------------------------------------------------------------------
# School settings
# ---------------------------------------------------------------------------
def configure_school_settings(period_type, stdout):
    """Configure SchoolSettings for the tenant."""
    stdout.write('  Configuring school settings...')
    settings = SchoolSettings.load()
    settings.academic_period_type = period_type
    settings.setup_completed = True
    settings.save()
    stdout.write(f'    - academic_period_type = {period_type}')


# ---------------------------------------------------------------------------
# Admin user
# ---------------------------------------------------------------------------
def ensure_admin_user(admin_email, admin_password, stdout):
    """Ensure a school admin user exists with the given credentials."""
    stdout.write('  Ensuring admin user...')
    user = User.objects.filter(email=admin_email).first()
    if user:
        stdout.write(f'    - Admin already exists: {admin_email}')
    else:
        user = User.objects.create_school_admin(
            email=admin_email,
            password=admin_password,
            first_name='School',
            last_name='Admin',
        )
        stdout.write(f'    - Created admin: {admin_email}')
    stdout.write(f'    - Password: {admin_password}')
    return user


# ---------------------------------------------------------------------------
# Academic year & periods
# ---------------------------------------------------------------------------
def create_academic_year(stdout):
    """Create the current academic year. Returns the AcademicYear instance."""
    stdout.write('  Creating academic year...')
    today = date.today()
    year_start = date(today.year if today.month >= 9 else today.year - 1, 9, 1)
    year_end = date(year_start.year + 1, 7, 31)

    academic_year, created = AcademicYear.objects.get_or_create(
        name=f'{year_start.year}/{year_end.year}',
        defaults={
            'start_date': year_start,
            'end_date': year_end,
            'is_current': True,
        },
    )
    label = 'Created' if created else 'Found existing'
    stdout.write(f'    - {label}: {academic_year.name}')
    return academic_year


def create_terms(academic_year, stdout):
    """Create 3 terms for a basic school."""
    stdout.write('  Creating terms...')
    start = academic_year.start_date
    terms_data = [
        ('First Term', 1, start, start + timedelta(days=90)),
        ('Second Term', 2, start + timedelta(days=100),
         start + timedelta(days=190)),
        ('Third Term', 3, start + timedelta(days=200),
         academic_year.end_date),
    ]
    for name, number, s, e in terms_data:
        term, created = Term.objects.get_or_create(
            academic_year=academic_year,
            term_number=number,
            defaults={
                'name': name,
                'start_date': s,
                'end_date': e,
                'is_current': (number == 1),
            },
        )
        label = 'Created' if created else 'Exists'
        stdout.write(f'    - {label}: {term.name}')


def create_semesters(academic_year, stdout):
    """Create 2 semesters for an SHS school."""
    stdout.write('  Creating semesters...')
    start = academic_year.start_date
    semesters_data = [
        ('Semester One', 1, start, start + timedelta(days=150)),
        ('Semester Two', 2, start + timedelta(days=160),
         academic_year.end_date),
    ]
    for name, number, s, e in semesters_data:
        sem, created = Term.objects.get_or_create(
            academic_year=academic_year,
            term_number=number,
            defaults={
                'name': name,
                'start_date': s,
                'end_date': e,
                'is_current': (number == 1),
            },
        )
        label = 'Created' if created else 'Exists'
        stdout.write(f'    - {label}: {sem.name}')


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------
def create_teachers(teacher_data, domain, stdout):
    """
    Create teachers from a deterministic list.

    teacher_data: list of dicts with keys:
        first_name, last_name, gender, title, staff_id
    domain: the tenant's primary domain (e.g., 'demoshs.localhost')
    """
    stdout.write('  Creating teachers...')
    created_count = 0
    for td in teacher_data:
        staff_id = td['staff_id']
        if Teacher.objects.filter(staff_id=staff_id).exists():
            stdout.write(f'    - Exists: {staff_id}')
            continue

        email = (
            f"{td['first_name'].lower()}.{td['last_name'].lower()}"
            f"@{domain}"
        )
        # Ensure unique email
        if User.objects.filter(email=email).exists():
            email = f"{td['first_name'].lower()}.{td['last_name'].lower()}"
            email += f".{staff_id.lower()}@{domain}"

        user = User.objects.create_teacher(
            email=email,
            password='Teacher@2026',
            first_name=td['first_name'],
            last_name=td['last_name'],
        )

        Teacher.objects.create(
            user=user,
            title=td['title'],
            first_name=td['first_name'],
            last_name=td['last_name'],
            gender=td['gender'],
            date_of_birth=date(1985, 1, 15) + timedelta(
                days=hash(staff_id) % 3650
            ),
            staff_id=staff_id,
            phone_number=f'+23324{abs(hash(staff_id)) % 9000000 + 1000000}',
            email=email,
            employment_date=date.today() - timedelta(days=365),
            status='active',
        )
        created_count += 1
        stdout.write(
            f'    - Created: {staff_id} '
            f'({td["first_name"]} {td["last_name"]})'
        )

    stdout.write(
        f'    Total teachers: {Teacher.objects.count()} '
        f'({created_count} new)'
    )


# ---------------------------------------------------------------------------
# Students & guardians
# ---------------------------------------------------------------------------
def create_students_and_guardians(per_class, houses, stdout):
    """
    Create students with guardians for every active class.

    per_class: number of students per class
    houses: list of House objects (can be empty for basic schools)
    """
    stdout.write('  Creating students and guardians...')
    classes = Class.objects.filter(is_active=True)
    academic_year = AcademicYear.objects.filter(is_current=True).first()

    student_count = 0
    for cls in classes:
        for i in range(per_class):
            admission_number = f'ADM-{cls.name}-{str(i + 1).zfill(3)}'

            if Student.objects.filter(
                admission_number=admission_number
            ).exists():
                continue

            gender = 'M' if i % 2 == 0 else 'F'
            first_names = (MALE_FIRST_NAMES if gender == 'M'
                           else FEMALE_FIRST_NAMES)
            first_name = first_names[
                (hash(admission_number) + i) % len(first_names)
            ]
            last_name = LAST_NAMES[
                (hash(admission_number) + i + 7) % len(LAST_NAMES)
            ]

            house = None
            if houses:
                house = houses[i % len(houses)]

            student = Student.objects.create(
                first_name=first_name,
                last_name=last_name,
                gender=gender,
                date_of_birth=date(2010, 3, 15) + timedelta(
                    days=(hash(admission_number) % 1800)
                ),
                admission_number=admission_number,
                admission_date=date.today() - timedelta(days=180),
                current_class=cls,
                house=house,
                residence_type='boarding' if houses else '',
                status='active',
            )
            student_count += 1

            # Enrollment
            if academic_year:
                Enrollment.objects.get_or_create(
                    student=student,
                    academic_year=academic_year,
                    defaults={
                        'class_assigned': cls,
                        'status': 'active',
                    },
                )

            # Guardian
            _create_guardian_for_student(student, last_name, i)

    stdout.write(f'    - Created {student_count} students')


def _create_guardian_for_student(student, family_name, index):
    """Create a guardian and link to a student."""
    guardian_gender = 'M' if index % 2 == 0 else 'F'
    if guardian_gender == 'M':
        guardian_first_names = MALE_FIRST_NAMES
    else:
        guardian_first_names = FEMALE_FIRST_NAMES
    guardian_first = guardian_first_names[
        (hash(student.admission_number) + 3) % len(guardian_first_names)
    ]
    phone = f'+23320{abs(hash(student.admission_number)) % 9000000 + 1000000}'

    guardian, _ = Guardian.objects.get_or_create(
        phone_number=phone,
        defaults={
            'full_name': f'{guardian_first} {family_name}',
            'occupation': OCCUPATIONS[
                abs(hash(phone)) % len(OCCUPATIONS)
            ],
            'address': f'{abs(hash(phone)) % 200 + 1} Main Road, Accra',
        },
    )

    relationship = 'father' if guardian_gender == 'M' else 'mother'
    StudentGuardian.objects.get_or_create(
        student=student,
        guardian=guardian,
        defaults={
            'relationship': relationship,
            'is_primary': True,
            'is_emergency_contact': True,
        },
    )


# ---------------------------------------------------------------------------
# Classrooms
# ---------------------------------------------------------------------------
def create_classrooms(stdout):
    """Create standard classrooms."""
    stdout.write('  Creating classrooms...')
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
    created = 0
    for name, code, capacity, room_type in rooms:
        _, was_created = Classroom.objects.get_or_create(
            name=name,
            defaults={
                'code': code,
                'capacity': capacity,
                'room_type': room_type,
                'is_active': True,
            },
        )
        if was_created:
            created += 1
    stdout.write(f'    - {created} new classrooms (total {Classroom.objects.count()})')


# ---------------------------------------------------------------------------
# Class-subject assignments
# ---------------------------------------------------------------------------
def create_class_subjects(stdout):
    """Assign seeded subjects to classes with teachers."""
    stdout.write('  Assigning subjects to classes...')
    teachers = list(Teacher.objects.filter(status='active'))
    if not teachers:
        stdout.write('    - No teachers found, skipping')
        return

    classes = Class.objects.filter(is_active=True)
    core_subjects = list(Subject.objects.filter(is_core=True, is_active=True))
    elective_subjects = list(
        Subject.objects.filter(is_core=False, is_active=True)
    )

    count = 0
    for cls in classes:
        # Assign all core subjects
        for subj in core_subjects:
            _, was_created = ClassSubject.objects.get_or_create(
                class_assigned=cls,
                subject=subj,
                defaults={
                    'teacher': teachers[count % len(teachers)],
                    'periods_per_week': 4,
                },
            )
            if was_created:
                count += 1

        # Assign up to 3 elective subjects
        sample_size = min(3, len(elective_subjects))
        if sample_size > 0:
            rng = random.Random(hash(cls.name))
            for subj in rng.sample(elective_subjects, sample_size):
                _, was_created = ClassSubject.objects.get_or_create(
                    class_assigned=cls,
                    subject=subj,
                    defaults={
                        'teacher': teachers[count % len(teachers)],
                        'periods_per_week': 3,
                    },
                )
                if was_created:
                    count += 1

    stdout.write(f'    - {count} new class-subject assignments')


# ---------------------------------------------------------------------------
# Assignments & scores
# ---------------------------------------------------------------------------
def create_assignments_and_scores(stdout):
    """Create 1 CA + 1 Exam per class-subject, with normally distributed scores."""
    stdout.write('  Creating assignments and scores...')
    term = Term.objects.filter(is_current=True).first()
    if not term:
        stdout.write('    - No current term found, skipping')
        return

    ca_category = AssessmentCategory.objects.filter(
        category_type='CLASS_SCORE'
    ).first()
    exam_category = AssessmentCategory.objects.filter(
        category_type='EXAM'
    ).first()

    if not ca_category or not exam_category:
        stdout.write('    - Assessment categories missing, skipping')
        return

    class_subjects = ClassSubject.objects.select_related(
        'class_assigned', 'subject'
    )

    assignment_count = 0
    score_count = 0
    rng = random.Random(42)

    for cs in class_subjects:
        students = Student.objects.filter(
            current_class=cs.class_assigned,
            status='active',
        )
        if not students.exists():
            continue

        # 1 Class Assessment
        ca_assignment, ca_created = Assignment.objects.get_or_create(
            assessment_category=ca_category,
            subject=cs.subject,
            term=term,
            name='Class Assessment 1',
            defaults={
                'points_possible': Decimal('30'),
                'date': term.start_date + timedelta(days=30),
            },
        )
        if ca_created:
            assignment_count += 1

        # 1 Exam
        exam_assignment, ex_created = Assignment.objects.get_or_create(
            assessment_category=exam_category,
            subject=cs.subject,
            term=term,
            name='End of Term Exam',
            defaults={
                'points_possible': Decimal('70'),
                'date': term.start_date + timedelta(days=80),
            },
        )
        if ex_created:
            assignment_count += 1

        # Scores
        for student in students:
            for assignment in [ca_assignment, exam_assignment]:
                _, was_created = Score.objects.get_or_create(
                    student=student,
                    assignment=assignment,
                    defaults={
                        'points': _random_score(
                            assignment.points_possible, rng
                        ),
                    },
                )
                if was_created:
                    score_count += 1

    stdout.write(f'    - {assignment_count} assignments, {score_count} scores')


def _random_score(max_points, rng):
    """Generate a normally distributed score (mean ~65%, sd ~15%)."""
    pct = max(5, min(98, rng.gauss(65, 15)))
    raw = float(max_points) * pct / 100
    return Decimal(str(round(raw, 2)))


# ---------------------------------------------------------------------------
# Seed commands
# ---------------------------------------------------------------------------
def run_seed_commands(schema_name, stdout):
    """Run seed_academics, seed_grading_data, seed_remark_templates."""
    stdout.write('  Running seed commands...')

    call_command('seed_academics', schema=schema_name, stdout=stdout)
    call_command('seed_grading_data', schema=schema_name, stdout=stdout)
    call_command('seed_remark_templates', tenant=schema_name, stdout=stdout)

    stdout.write('    - Seed commands complete')
