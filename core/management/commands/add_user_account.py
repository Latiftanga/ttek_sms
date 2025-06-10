from core.models import School
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from core.models import Teacher, Student
from django.utils import timezone


class Command(BaseCommand):
    help = 'Add user account to existing teacher or student profile'

    def add_arguments(self, parser):
        parser.add_argument('--type', required=True, choices=['teacher', 'student'],
                            help='Profile type')
        parser.add_argument('--id', required=True,
                            help='Employee ID or Student ID')

    def handle(self, *args, **options):
        profile_type = options['type']
        profile_id = options['id']

        try:
            if profile_type == 'teacher':
                profile = Teacher.objects.get(employee_id=profile_id)
            else:
                profile = Student.objects.get(student_id=profile_id)

            if profile.has_user_account():
                self.stdout.write(
                    self.style.WARNING(
                        f'{profile_type.title()} already has a user account')
                )
                return

            user, password = profile.create_user_account()

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created user account for {profile.get_full_name()}')
            )
            self.stdout.write(
                self.style.SUCCESS(f'Username: {user.username}')
            )
            self.stdout.write(
                self.style.SUCCESS(f'Password: {password}')
            )
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  Save this password - it won\'t be shown again!')
            )

        except Teacher.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'Teacher with employee ID {profile_id} not found')
            )
        except Student.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'Student with student ID {profile_id} not found')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating user account: {str(e)}')
            )


User = get_user_model()


class Command(BaseCommand):
    help = 'Create a school admin user'

    def add_arguments(self, parser):
        parser.add_argument('--school-code', required=True, help='School code')
        parser.add_argument('--admin-username',
                            help='Custom username for non-teacher admin')
        parser.add_argument('--is-teacher', action='store_true',
                            help='Admin is also a teacher')
        parser.add_argument(
            '--employee-id', help='Employee ID (required if admin is teacher)')
        parser.add_argument(
            '--subjects', help='Comma-separated subjects if admin is teacher')
        parser.add_argument('--qualification',
                            help='Teacher qualification if admin is teacher')

    def handle(self, *args, **options):
        try:
            school = School.objects.get(code=options['school_code'])
        except School.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'School with code {options["school_code"]} not found')
            )
            return

        profile_data = {}
        if options['is_teacher']:
            if not options['employee_id']:
                self.stdout.write(
                    self.style.ERROR('Employee ID required for teacher admin')
                )
                return

            profile_data = {
                'employee_id': options['employee_id'],
                'subjects': options['subjects'].split(',') if options['subjects'] else [],
                'qualification': options['qualification'] or 'Admin',
                'hire_date': timezone.now().date(),
            }

        try:
            admin_user, password = User.objects.create_school_admin(
                school=school,
                is_teacher=options['is_teacher'],
                admin_username=options['admin_username'],
                **profile_data
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created admin user for {school.name}'
                )
            )
            self.stdout.write(
                self.style.SUCCESS(f'Username: {admin_user.username}')
            )
            self.stdout.write(
                self.style.SUCCESS(f'Password: {password}')
            )
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  Save this password - it won\'t be shown again!')
            )

            if options['is_teacher']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Admin is also a teacher with Employee ID: {options["employee_id"]}')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating admin: {str(e)}')
            )
