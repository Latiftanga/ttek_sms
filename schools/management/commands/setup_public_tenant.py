import os
import getpass
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.conf import settings
from schools.models import School, Domain


class Command(BaseCommand):
    help = 'Set up the public tenant with domain and superuser for platform administration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--domain',
            help='Primary domain for the platform (e.g., ttek-sms.com)'
        )
        parser.add_argument(
            '--email',
            help='Superuser email address'
        )
        parser.add_argument(
            '--password',
            help='Superuser password (will prompt if not provided)'
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Run without prompts (uses environment variables or defaults)'
        )

    def handle(self, *args, **options):
        is_production = not settings.DEBUG
        no_input = options.get('no_input', False)

        self.stdout.write(self.style.NOTICE('\n' + '=' * 60))
        self.stdout.write(self.style.NOTICE('  TTEK SMS Platform Setup'))
        self.stdout.write(self.style.NOTICE('=' * 60 + '\n'))

        if is_production:
            self.stdout.write(self.style.WARNING('Running in PRODUCTION mode\n'))
        else:
            self.stdout.write(self.style.SUCCESS('Running in DEVELOPMENT mode\n'))

        # Step 1: Get or create public tenant
        self.stdout.write(self.style.HTTP_INFO('Step 1: Setting up public tenant...\n'))
        public_tenant = self._setup_public_tenant()

        # Step 2: Configure domain
        self.stdout.write(self.style.HTTP_INFO('\nStep 2: Configuring domain...\n'))
        domain = self._setup_domain(public_tenant, options, is_production, no_input)

        # Step 3: Create superuser
        self.stdout.write(self.style.HTTP_INFO('\nStep 3: Creating superuser...\n'))
        self._setup_superuser(options, no_input)

        # Summary
        self._print_summary(domain)

    def _setup_public_tenant(self):
        """Create or get the public tenant."""
        public_tenant = School.objects.filter(schema_name='public').first()

        if not public_tenant:
            public_tenant = School.objects.create(
                schema_name='public',
                name='TTEK SMS Platform',
                short_name='TTEK',
            )
            self.stdout.write(self.style.SUCCESS('  ✓ Public tenant created'))
        else:
            self.stdout.write(f'  ✓ Public tenant exists: {public_tenant.name}')

        return public_tenant

    def _setup_domain(self, public_tenant, options, is_production, no_input):
        """Configure the primary domain for the platform."""
        # Determine domain
        domain_name = options.get('domain')

        if not domain_name:
            # Check environment variable
            domain_name = os.getenv('PUBLIC_DOMAIN')

        if not domain_name and not no_input:
            # Prompt user
            if is_production:
                default = 'example.com'
                self.stdout.write('  Enter your production domain (e.g., ttek-sms.com)')
            else:
                default = 'localhost'
                self.stdout.write('  Enter domain for development')

            domain_name = input(f'  Domain [{default}]: ').strip() or default

        if not domain_name:
            domain_name = 'localhost'

        # Create or update domain
        existing_domain = Domain.objects.filter(domain=domain_name).first()

        if not existing_domain:
            Domain.objects.create(
                domain=domain_name,
                tenant=public_tenant,
                is_primary=True,
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Domain created: {domain_name}'))
        elif existing_domain.tenant.schema_name != 'public':
            existing_domain.tenant = public_tenant
            existing_domain.is_primary = True
            existing_domain.save()
            self.stdout.write(self.style.SUCCESS(f'  ✓ Domain updated: {domain_name}'))
        else:
            self.stdout.write(f'  ✓ Domain exists: {domain_name}')

        # Add www subdomain for production
        if is_production and domain_name != 'localhost' and not domain_name.startswith('www.'):
            www_domain = f'www.{domain_name}'
            if not Domain.objects.filter(domain=www_domain).exists():
                Domain.objects.create(
                    domain=www_domain,
                    tenant=public_tenant,
                    is_primary=False,
                )
                self.stdout.write(self.style.SUCCESS(f'  ✓ WWW domain created: {www_domain}'))

        return domain_name

    def _setup_superuser(self, options, no_input):
        """Create a superuser for the platform."""
        User = get_user_model()

        # Check if superuser already exists
        if User.objects.filter(is_superuser=True).exists():
            existing = User.objects.filter(is_superuser=True).first()
            self.stdout.write(f'  ✓ Superuser exists: {existing.email}')
            return

        email = options.get('email') or os.getenv('SUPERUSER_EMAIL')
        password = options.get('password') or os.getenv('SUPERUSER_PASSWORD')

        if not no_input:
            if not email:
                email = input('  Superuser email: ').strip()

            if not password:
                while True:
                    password = getpass.getpass('  Superuser password: ')
                    password_confirm = getpass.getpass('  Confirm password: ')

                    if password != password_confirm:
                        self.stdout.write(self.style.ERROR('  Passwords do not match. Try again.'))
                        continue

                    try:
                        validate_password(password)
                        break
                    except ValidationError as e:
                        self.stdout.write(self.style.ERROR(f'  {"; ".join(e.messages)}'))
                        continue

        if not email or not password:
            self.stdout.write(self.style.WARNING('  ⚠ Skipping superuser creation (no credentials provided)'))
            self.stdout.write('    Run: python manage.py createsuperuser')
            return

        try:
            user = User.objects.create_superuser(
                email=email,
                password=password,
                first_name='Platform',
                last_name='Admin',
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Superuser created: {email}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Failed to create superuser: {e}'))

    def _print_summary(self, domain):
        """Print setup summary."""
        protocol = 'http' if settings.DEBUG else 'https'
        port = ':8000' if settings.DEBUG else ''

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('  Setup Complete!'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'\n  Platform URL: {protocol}://{domain}{port}')
        self.stdout.write(f'  Admin Panel:  {protocol}://{domain}{port}/admin/')
        self.stdout.write('\n  To create schools, log into the admin panel')
        self.stdout.write('  and add new School entries.\n')
