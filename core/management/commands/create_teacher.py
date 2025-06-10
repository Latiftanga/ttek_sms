from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import School, Teacher
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a teacher profile with optional user account'

    def add_arguments(self, parser):
        parser.add_argument('--school-code', required=True, help='School code')
        parser.add_argument('--employee-id', required=True, help='Employee ID')
        parser.add_argument('--first-name', required=True, help='First name')
        parser.add_argument('--last-name', required=True, help='Last name')
        parser.add_argument('--subjects', help='Comma-separated subjects')
        parser.add_argument('--qualification', help='Teacher qualification')
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

        teacher_data = {
            'employee_id': options['employee_id'],
            'first_name': options['first_name'],
            'last_name': options['last_name'],
            'subjects': options['subjects'].split(',') if options['subjects'] else [],
            'qualification': options['qualification'] or '',
            'hire_date': timezone.now().date(),
            'gender': 'M',  # Default, should be updated via admin
            'date_of_birth': timezone.now().date(),  # Default, should be updated
        }

        create_user_account = not options['no_user_account']

        try:
            teacher_profile, user, password = User.objects.create_teacheruser(
                school=school,
                create_user_account=create_user_account,
                **teacher_data
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created teacher: {teacher_profile.get_full_name()}')
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
                        'No user account created. Teacher profile only.')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating teacher: {str(e)}')
            )
