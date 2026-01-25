import os
import getpass
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import connection
from schools.models import School, Domain


class Command(BaseCommand):
    help = 'Create a school tenant for testing or production'

    def add_arguments(self, parser):
        parser.add_argument(
            '--name',
            help='School name (e.g., "Demo School")'
        )
        parser.add_argument(
            '--subdomain',
            help='Subdomain/schema for the school (e.g., "demo")'
        )
        parser.add_argument(
            '--admin-email',
            help='School admin email address'
        )
        parser.add_argument(
            '--admin-password',
            help='School admin password'
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Run without prompts'
        )

    def handle(self, *args, **options):
        no_input = options.get('no_input', False)

        self.stdout.write(self.style.NOTICE('\n' + '=' * 60))
        self.stdout.write(self.style.NOTICE('  Create New School'))
        self.stdout.write(self.style.NOTICE('=' * 60 + '\n'))

        # Get school details
        name = options.get('name')
        subdomain = options.get('subdomain')
        admin_email = options.get('admin_email')
        admin_password = options.get('admin_password')

        if not no_input:
            if not name:
                name = input('  School name: ').strip()
            if not subdomain:
                suggested = name.lower().replace(' ', '_')[:20] if name else 'school'
                subdomain = input(f'  Subdomain [{suggested}]: ').strip() or suggested
            if not admin_email:
                admin_email = input('  Admin email: ').strip()
            if not admin_password:
                while True:
                    admin_password = getpass.getpass('  Admin password: ')
                    password_confirm = getpass.getpass('  Confirm password: ')
                    if admin_password != password_confirm:
                        self.stdout.write(self.style.ERROR('  Passwords do not match. Try again.'))
                        continue
                    try:
                        validate_password(admin_password)
                        break
                    except ValidationError as e:
                        self.stdout.write(self.style.ERROR(f'  {"; ".join(e.messages)}'))

        # Validate inputs
        if not all([name, subdomain, admin_email, admin_password]):
            self.stdout.write(self.style.ERROR('\n  All fields are required!'))
            return

        # Clean subdomain
        subdomain = subdomain.lower().replace('-', '_').replace(' ', '_')

        # Determine the full domain
        base_domain = os.getenv('BASE_DOMAIN', 'localhost')
        if base_domain in ['localhost', '127.0.0.1']:
            full_domain = f'{subdomain}.localhost'
        else:
            full_domain = f'{subdomain}.{base_domain}'

        self.stdout.write(f'\n  Creating school: {name}')
        self.stdout.write(f'  Schema: {subdomain}')
        self.stdout.write(f'  Domain: {full_domain}\n')

        # Check if school already exists
        existing = School.objects.filter(schema_name=subdomain).first()
        if existing:
            self.stdout.write(self.style.WARNING(f'  School with schema "{subdomain}" already exists'))
            # Check if domain exists
            if not Domain.objects.filter(domain=full_domain).exists():
                Domain.objects.create(domain=full_domain, tenant=existing, is_primary=True)
                self.stdout.write(self.style.SUCCESS(f'  Added domain: {full_domain}'))
            return

        # Create the school tenant
        school = School.objects.create(
            schema_name=subdomain,
            name=name,
            short_name=subdomain.upper()[:20],
        )
        self.stdout.write(self.style.SUCCESS(f'  ✓ School created: {school.name}'))

        # Create domain
        Domain.objects.create(domain=full_domain, tenant=school, is_primary=True)
        self.stdout.write(self.style.SUCCESS(f'  ✓ Domain created: {full_domain}'))

        # Switch to tenant schema to create school admin user
        connection.set_tenant(school)

        User = get_user_model()
        if not User.objects.filter(email=admin_email).exists():
            User.objects.create_school_admin(
                email=admin_email,
                password=admin_password,
                first_name='School',
                last_name='Admin',
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ School admin created: {admin_email}'))
        else:
            self.stdout.write(f'  School admin already exists: {admin_email}')

        # Summary
        protocol = 'http' if settings.DEBUG else 'https'
        port = ':8000' if settings.DEBUG else ''

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('  School Created Successfully!'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'\n  URL: {protocol}://{full_domain}{port}')
        self.stdout.write(f'  Admin Email: {admin_email}')
        self.stdout.write(f'  Admin Password: {"*" * len(admin_password)}')
        self.stdout.write(self.style.NOTICE('\n  Note: This is a SCHOOL ADMIN (not platform superuser).'))
        self.stdout.write(self.style.NOTICE('  They can only access this school\'s data.\n'))

        if settings.DEBUG and base_domain == 'localhost':
            self.stdout.write(self.style.WARNING('  Add this to /etc/hosts for local development:'))
            self.stdout.write(f'  127.0.0.1  {full_domain}\n')
