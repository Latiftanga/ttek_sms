from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Tenant, Student, Teacher
from django.utils import timezone
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Create sample data for testing multi-tenant functionality'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Creating sample data...'))

        # Create sample schools
        schools_data = [
            {
                'name': 'T.I. Ahmadiyya Senior High School',
                'code': 'TIA',
                'school_type': 'shs',
                'ownership': 'mission',
                'region': 'greater_accra',
                'district': 'Tema West',
                'town': 'Tema',
                'headmaster_name': 'Mr. Abdul Rahman',
                'email': 'admin@tia-shs.edu.gh',
                'phone_primary': '+233244123456',
                'subdomain': 'tia',
                'motto': 'Knowledge, Service, Unity'
            },
            {
                'name': 'Ghana International School',
                'code': 'GIS',
                'school_type': 'combined',
                'ownership': 'international',
                'region': 'greater_accra',
                'district': 'Accra Metropolitan',
                'town': 'East Legon',
                'headmaster_name': 'Dr. Sarah Johnson',
                'email': 'admin@gis.edu.gh',
                'phone_primary': '+233302789456',
                'subdomain': 'gis',
                'motto': 'Excellence in Education'
            }
        ]

        schools = []
        for school_data in schools_data:
            school, created = Tenant.objects.get_or_create(
                code=school_data['code'],
                defaults=school_data
            )
            schools.append(school)
            status = "Created" if created else "Already exists"
            self.stdout.write(f"{status}: {school.name}")

        # Create admin users for each school
        for school in schools:
            admin_username = f"admin_{school.code.lower()}"
            admin_user, created = User.objects.get_or_create(
                username=admin_username,
                defaults={
                    'school': school,
                    'email': school.email,
                    'is_active': True,
                    'is_staff': True,
                    'is_admin': True,
                    'is_teacher': True,
                }
            )
            if created:
                admin_user.set_password('admin123')  # Set a default password
                admin_user.save()
                self.stdout.write(
                    f"Created admin user: {admin_username} (password: admin123)")
            else:
                self.stdout.write(
                    f"Admin user already exists: {admin_username}")

        # Create sample students
        sample_students = [
            {'first_name': 'Amina', 'last_name': 'Mohammed', 'gender': 'F'},
            {'first_name': 'Kwame', 'last_name': 'Asante', 'gender': 'M'},
            {'first_name': 'Fatima', 'last_name': 'Abdul', 'gender': 'F'},
            {'first_name': 'Ibrahim', 'last_name': 'Bello', 'gender': 'M'},
            {'first_name': 'Ama', 'last_name': 'Osei', 'gender': 'F'},
        ]

        for school in schools:
            for i, student_data in enumerate(sample_students):
                student_data_full = {
                    **student_data,
                    'school': school,
                    'date_of_birth': timezone.now().date().replace(year=2006),
                    'year_admitted': 2024,
                    'email': f"{student_data['first_name'].lower()}.{student_data['last_name'].lower()}@{school.code.lower()}.edu.gh",
                    'phone': f"+23324{random.randint(1000000, 9999999)}",
                    'address': f"{random.randint(1, 100)} Main Street, {school.town}",
                }

                student, created = Student.objects.get_or_create(
                    school=school,
                    first_name=student_data['first_name'],
                    last_name=student_data['last_name'],
                    defaults=student_data_full
                )
                if created:
                    self.stdout.write(
                        f"Created student: {student.get_full_name()} ({student.student_id})")

        # Create sample teachers
        sample_teachers = [
            {'first_name': 'John', 'last_name': 'Doe', 'gender': 'M'},
            {'first_name': 'Jane', 'last_name': 'Smith', 'gender': 'F'},
            {'first_name': 'Michael', 'last_name': 'Brown', 'gender': 'M'},
        ]

        for school in schools:
            for teacher_data in sample_teachers:
                teacher_data_full = {
                    **teacher_data,
                    'school': school,
                    'date_of_birth': timezone.now().date().replace(year=1980),
                    'email': f"{teacher_data['first_name'].lower()}.{teacher_data['last_name'].lower()}@{school.code.lower()}.edu.gh",
                    'phone': f"+23324{random.randint(1000000, 9999999)}",
                    'address': f"{random.randint(1, 100)} Teacher Street, {school.town}",
                }

                teacher, created = Teacher.objects.get_or_create(
                    school=school,
                    first_name=teacher_data['first_name'],
                    last_name=teacher_data['last_name'],
                    defaults=teacher_data_full
                )
                if created:
                    self.stdout.write(
                        f"Created teacher: {teacher.get_full_name()} ({teacher.teacher_id})")

        self.stdout.write(self.style.SUCCESS(
            'Sample data creation completed!'))
        self.stdout.write(self.style.WARNING('Admin credentials:'))
        for school in schools:
            self.stdout.write(f"School: {school.name}")
            self.stdout.write(f"  Username: admin_{school.code.lower()}")
            self.stdout.write(f"  Password: admin123")
            self.stdout.write(
                f"  URL: http://{school.subdomain}.localhost:8000/")
            self.stdout.write("")
