from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import School, Teacher, Student
from django.utils import timezone
import random

User = get_user_model()

class Command(BaseCommand):
    help = 'Create demo data for testing'

    def add_arguments(self, parser):
        parser.add_argument('--school-code', required=True, help='School code')
        parser.add_argument('--teachers', type=int, default=5, help='Number of teachers to create')
        parser.add_argument('--students', type=int, default=20, help='Number of students to create')

    def handle(self, *args, **options):
        try:
            school = School.objects.get(code=options['school_code'])
        except School.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'School with code {options["school_code"]} not found')
            )
            return

        # Sample data
        teacher_names = [
            ('John', 'Doe'), ('Jane', 'Smith'), ('Michael', 'Johnson'),
            ('Sarah', 'Williams'), ('David', 'Brown'), ('Lisa', 'Davis'),
            ('Robert', 'Miller'), ('Jennifer', 'Wilson'), ('William', 'Moore')
        ]
        
        student_names = [
            ('Amina', 'Mohammed'), ('Kwame', 'Asante'), ('Fatima', 'Abdul'),
            ('Ibrahim', 'Bello'), ('Aisha', 'Osei'), ('Emmanuel', 'Mensah'),
            ('Zainab', 'Yakubu'), ('Daniel', 'Adjei'), ('Rahinatu', 'Alhassan'),
            ('Prince', 'Owusu'), ('Mariam', 'Issah'), ('Samuel', 'Appiah'),
            ('Nafisa', 'Iddrisu'), ('Joseph', 'Nkrumah'), ('Halima', 'Sulemana'),
            ('Francis', 'Boateng'), ('Salamatu', 'Musah'), ('Richard', 'Amponsah'),
            ('Faridah', 'Abdallah'), ('George', 'Manu')
        ]
        
        subjects_list = [
            ['math', 'physics'], ['english', 'literature'], ['chemistry', 'biology'],
            ['social_studies', 'history'], ['ict', 'math'], ['french', 'english'],
            ['physical_education'], ['religious_studies'], ['creative_arts']
        ]
        
        # Create teachers
        for i in range(options['teachers']):
            first_name, last_name = teacher_names[i % len(teacher_names)]
            employee_id = f"{school.code}{(i+2):03d}"  # Start from 002 (001 is admin)
            
            # Create some with accounts, some without
            create_account = random.choice([True, False])
            
            teacher_data = {
                'employee_id': employee_id,
                'first_name': first_name,
                'last_name': last_name,
                'subjects': subjects_list[i % len(subjects_list)],
                'qualification': random.choice(['B.Ed', 'B.A', 'B.Sc', 'M.Ed', 'M.A']),
                'experience_years': random.randint(1, 15),
                'hire_date': timezone.now().date(),
                'gender': random.choice(['M', 'F']),
                'date_of_birth': '1985-01-01',
                'phone': f"024{random.randint(1000000, 9999999)}"
            }
            
            teacher_profile, user, password = User.objects.create_teacheruser(
                school=school,
                create_user_account=create_account,
                **teacher_data
            )
            
            status = "with account" if user else "profile only"
            self.stdout.write(f'✓ Created teacher: {teacher_profile.get_full_name()} ({status})')
        
        # Create students
        for i in range(options['students']):
            first_name, last_name = student_names[i % len(student_names)]
            student_id = f"{school.code}24{(i+1):03d}"  # 2024 batch
            
            # Create some with accounts, some without
            create_account = random.choice([True, True, False])  # 2/3 chance of having account
            
            student_data = {
                'student_id': student_id,
                'first_name': first_name,
                'last_name': last_name,
                'class_level': random.choice(['shs1', 'shs2', 'shs3']),
                'year_admitted': 2024,
                'gender': random.choice(['M', 'F']),
                'date_of_birth': f"200{random.randint(6, 8)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
                'phone': f"055{random.randint(1000000, 9999999)}" if random.choice([True, False]) else None
            }
            
            student_profile, user, password = User.objects.create_studentuser(
                school=school,
                create_user_account=create_account,
                **student_data
            )
            
            status = "with account" if user else "profile only"
            self.stdout.write(f'✓ Created student: {student_profile.get_full_name()} ({status})')
        
        self.stdout.write(
            self.style.SUCCESS(f'\n🎉 Demo data created for {school.name}!')
        )
        self.stdout.write(
            self.style.SUCCESS(f'Teachers: {options["teachers"]} | Students: {options["students"]}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'Visit: {school.get_login_url}')
        )
