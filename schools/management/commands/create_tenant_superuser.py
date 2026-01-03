from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context
from schools.models import School


class Command(BaseCommand):
    help = 'Create a superuser for a specific tenant (schema)'

    def add_arguments(self, parser):
        parser.add_argument('--schema', type=str, required=True,
                          help='Schema name (e.g., "public" or tenant schema)')
        parser.add_argument('--username', type=str, required=True)
        parser.add_argument('--email', type=str, required=True)
        parser.add_argument('--password', type=str, required=True)

    def handle(self, *args, **options):
        schema = options['schema']
        username = options['username']
        email = options['email']
        password = options['password']

        # Verify schema exists
        if schema != 'public':
            tenant = School.objects.filter(schema_name=schema).first()
            if not tenant:
                raise CommandError(f'Tenant with schema "{schema}" not found')
            self.stdout.write(f'Creating superuser for tenant: {tenant.name}')
        else:
            self.stdout.write('Creating superuser for public schema')

        User = get_user_model()

        with schema_context(schema):
            if User.objects.filter(username=username).exists():
                self.stdout.write(self.style.WARNING(f'User "{username}" already exists'))
                return

            if User.objects.filter(email=email).exists():
                self.stdout.write(self.style.WARNING(f'Email "{email}" already exists'))
                return

            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )
            self.stdout.write(self.style.SUCCESS(f'Superuser "{username}" created successfully'))
