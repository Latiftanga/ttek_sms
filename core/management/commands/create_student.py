from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import School, Student
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a student profile with optional user account'

    def add_arguments(self, parser):
        parser.add_argument('--school-code', required=True, help='School code')
        parser.add_argument('--student-id', required=True, help='Student ID')
        parser.add_argument('--first-name', required=True, help='First name')
        parser.add_argument('--last-name', required=True, help='Last name')
        parser.add_argument('--class-level', help='Class level')
        parser.add_argument('--no-user-account', action='store_true',
                            help='Create profile only, no user account')

    def handle(self, *args, **options):
        try:
            school = School.objects.get(code=options['school_code'])
        except School.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'School with code {options["school_code"]} not found')
            )
            return

        student_data = {
            'student_id': options['student_id'],
            'first_name': options['first_name'],
            'last_name': options['last_name'],
            'class_level': options['class_level'] or 'shs1',
            'year_admitted': timezone.now().year,
            'gender': 'M',  # Default, should be updated via admin
            'date_of_birth': timezone.now().date(),  # Default, should be updated
        }

        create_user_account = not options['no_user_account']

        try:
            student_profile, user, password = User.objects.create_studentuser(
                school=school,
                create_user_account=create_user_account,
                **student_data
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created student: {student_profile.get_full_name()}')
            )

            if user:
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
            else:
                self.stdout.write(
                    self.style.WARNING(
                        'No user account created. Student profile only.')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating student: {str(e)}')
            )
