import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Create a superuser using environment variables'

    def handle(self, *args, **options):
        schema = os.getenv('SUPERUSER_SCHEMA', 'public')
        username = os.getenv('SUPERUSER_USERNAME')
        email = os.getenv('SUPERUSER_EMAIL')
        password = os.getenv('SUPERUSER_PASSWORD')

        if not all([username, email, password]):
            raise CommandError(
                'Missing environment variables. Required:\n'
                '  SUPERUSER_USERNAME\n'
                '  SUPERUSER_EMAIL\n'
                '  SUPERUSER_PASSWORD\n'
                'Optional:\n'
                '  SUPERUSER_SCHEMA (defaults to "public")'
            )

        self.stdout.write(f'Creating superuser in schema: {schema}')
        self.stdout.write(f'Username: {username}, Email: {email}')

        User = get_user_model()

        with schema_context(schema):
            if User.objects.filter(username=username).exists():
                self.stdout.write(self.style.WARNING(f'User "{username}" already exists in {schema}'))
                return

            if User.objects.filter(email=email).exists():
                self.stdout.write(self.style.WARNING(f'Email "{email}" already taken in {schema}'))
                return

            User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )
            self.stdout.write(self.style.SUCCESS(f'Superuser "{username}" created in schema "{schema}"'))
