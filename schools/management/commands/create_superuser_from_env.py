import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Create superuser from environment variables'

    def handle(self, *args, **options):
        email = os.getenv('SUPERUSER_EMAIL')
        password = os.getenv('SUPERUSER_PASSWORD')

        self.stdout.write(f'SUPERUSER_EMAIL env: {"SET" if email else "NOT SET"}')
        self.stdout.write(f'SUPERUSER_PASSWORD env: {"SET" if password else "NOT SET"}')

        if not all([email, password]):
            self.stdout.write(self.style.WARNING(
                'SUPERUSER_EMAIL and SUPERUSER_PASSWORD must be set'
            ))
            return

        User = get_user_model()

        # Create superuser in public schema
        try:
            with schema_context('public'):
                self.stdout.write(f'Checking if user {email} exists...')
                existing_user = User.objects.filter(email=email).first()

                if existing_user:
                    self.stdout.write(f'User {email} exists, updating password...')
                    existing_user.set_password(password)
                    existing_user.is_superuser = True
                    existing_user.is_staff = True
                    existing_user.is_active = True
                    existing_user.save()
                    self.stdout.write(self.style.SUCCESS(f'Password updated for {email}'))
                    return

                self.stdout.write(f'Creating superuser {email}...')
                user = User.objects.create_superuser(
                    email=email,
                    password=password
                )
                self.stdout.write(self.style.SUCCESS(f'Superuser {email} created successfully'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error creating superuser: {e}'))
