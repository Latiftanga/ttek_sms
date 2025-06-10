from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import School
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = 'Quickly set up a school with admin user'

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True, help='School name')
        parser.add_argument(
            '--code', help='School code (auto-generated if not provided)')
        parser.add_argument(
            '--subdomain', help='Subdomain (auto-generated if not provided)')
        parser.add_argument('--domain', help='Custom domain (optional)')
        parser.add_argument('--region', default='greater_accra', help='Region')
        parser.add_argument('--admin-username',
                            help='Admin username (defaults to admin_<code>)')
        parser.add_argument('--admin-teacher',
                            action='store_true', help='Make admin a teacher')
        parser.add_argument(
            '--employee-id', help='Employee ID if admin is teacher')

    def handle(self, *args, **options):
        # Determine school code
        if options['code']:
            school_code = options['code']
        else:
            # Generate code from name, handling dots and special chars
            name = options['name']
            words = name.replace('.', '').split()
            meaningful_words = [word for word in words if len(
                word) > 1 or word.upper() in ['I', 'A']]
            school_code = ''.join([word[0].upper()
                                  for word in meaningful_words[:3]])

            # Ensure we have at least 2 characters
            if len(school_code) < 2:
                first_word = words[0].replace('.', '') if words else 'SCH'
                school_code = first_word[:3].upper()

        # Determine subdomain
        if options['subdomain']:
            subdomain = options['subdomain']
        elif not options['domain']:
            # Generate subdomain from code
            subdomain = ''.join(c for c in school_code if c.isalnum()).lower()
        else:
            subdomain = None

        # Create school
        school_data = {
            'name': options['name'],
            'code': school_code,
            'school_type': 'shs',
            'ownership': 'public',
            'region': options['region'],
            'district': 'Sample District',
            'town': 'Sample Town',
            'headmaster_name': 'Headmaster',
            'email': f"admin@{subdomain or 'school'}.edu.gh",
            'phone_primary': '0244000000',
        }

        if subdomain:
            school_data['subdomain'] = subdomain
        if options['domain']:
            school_data['domain'] = options['domain']

        school = School.objects.create(**school_data)

        self.stdout.write(
            self.style.SUCCESS(
                f'✓ Created school: {school.name} (Code: {school.code})')
        )
        self.stdout.write(
            self.style.SUCCESS(f'✓ Subdomain: {school.subdomain}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'✓ Full domain: {school.get_tenant_domain}')
        )

        # Create admin user
        admin_username = options.get(
            'admin_username') or f"admin_{school.code.lower()}"

        if options['admin_teacher']:
            if not options['employee_id']:
                employee_id = f"{school.code}001"
            else:
                employee_id = options['employee_id']

            admin_user, password = User.objects.create_school_admin(
                school=school,
                is_teacher=True,
                employee_id=employee_id,
                subjects=["administration"],
                qualification="Administrator",
                hire_date=timezone.now().date(),
                first_name="Admin",
                last_name="User",
                gender="M",
                date_of_birth="1980-01-01"
            )
        else:
            admin_user, password = User.objects.create_school_admin(
                school=school,
                is_teacher=False,
                admin_username=admin_username
            )

        self.stdout.write(
            self.style.SUCCESS(f'✓ Created admin user: {admin_user.username}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'✓ Password: {password}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'✓ Login URL: {school.get_login_url}')
        )
        self.stdout.write(
            self.style.WARNING(
                '⚠️  Save the password - it won\'t be shown again!')
        )
