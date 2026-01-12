import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import connection
from schools.models import School, Domain


class Command(BaseCommand):
    help = 'Create a demo school tenant for development/testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--name',
            default='Demo School',
            help='School name (default: Demo School)'
        )
        parser.add_argument(
            '--subdomain',
            default='demo',
            help='Subdomain for the school (default: demo)'
        )
        parser.add_argument(
            '--admin-email',
            default='admin@demo.localhost',
            help='Admin user email'
        )
        parser.add_argument(
            '--admin-password',
            default='admin123',
            help='Admin user password'
        )

    def handle(self, *args, **options):
        name = options['name']
        subdomain = options['subdomain']
        admin_email = options['admin_email']
        admin_password = options['admin_password']

        # Determine the full domain
        base_domain = os.getenv('BASE_DOMAIN', 'localhost')
        if base_domain in ['localhost', '127.0.0.1']:
            full_domain = f'{subdomain}.localhost'
        else:
            full_domain = f'{subdomain}.{base_domain}'

        self.stdout.write(f'Creating demo school: {name}')
        self.stdout.write(f'Domain: {full_domain}')

        # Check if school already exists
        existing = School.objects.filter(schema_name=subdomain).first()
        if existing:
            self.stdout.write(self.style.WARNING(f'School with schema "{subdomain}" already exists'))
            # Check if domain exists
            domain = Domain.objects.filter(domain=full_domain).first()
            if not domain:
                Domain.objects.create(
                    domain=full_domain,
                    tenant=existing,
                    is_primary=True,
                )
                self.stdout.write(self.style.SUCCESS(f'Added domain: {full_domain}'))
            return

        # Create the school tenant
        school = School.objects.create(
            schema_name=subdomain,
            name=name,
            short_name=subdomain.upper(),
        )
        self.stdout.write(self.style.SUCCESS(f'Created school: {school.name}'))

        # Create domain
        Domain.objects.create(
            domain=full_domain,
            tenant=school,
            is_primary=True,
        )
        self.stdout.write(self.style.SUCCESS(f'Created domain: {full_domain}'))

        # Switch to tenant schema to create school admin user
        connection.set_tenant(school)

        User = get_user_model()
        if not User.objects.filter(email=admin_email).exists():
            # Use create_school_admin() for tenant-specific admin (NOT superuser)
            user = User.objects.create_school_admin(
                email=admin_email,
                password=admin_password,
                first_name='School',
                last_name='Admin',
            )
            self.stdout.write(self.style.SUCCESS(f'Created school admin: {admin_email}'))
        else:
            self.stdout.write(f'School admin already exists: {admin_email}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write(self.style.SUCCESS('Demo school created successfully!'))
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write('')
        self.stdout.write(f'  URL: http://{full_domain}:8000')
        self.stdout.write(f'  Admin Email: {admin_email}')
        self.stdout.write(f'  Admin Password: {admin_password}')
        self.stdout.write('')
        self.stdout.write(self.style.NOTICE('Note: This is a SCHOOL ADMIN (not superuser).'))
        self.stdout.write(self.style.NOTICE('They can only access this school\'s data.'))
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Add this to /etc/hosts for local development:'))
        self.stdout.write(f'  127.0.0.1  {full_domain}')
        self.stdout.write('')
