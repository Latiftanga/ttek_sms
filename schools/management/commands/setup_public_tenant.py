import os
from django.core.management.base import BaseCommand
from schools.models import School, Domain


class Command(BaseCommand):
    help = 'Create public tenant and register domain'

    def handle(self, *args, **options):
        # Get domain from environment or use default
        public_domain = os.getenv('PUBLIC_DOMAIN', 'localhost')

        # Check if public tenant exists
        public_tenant = School.objects.filter(schema_name='public').first()

        if not public_tenant:
            self.stdout.write('Creating public tenant...')
            public_tenant = School.objects.create(
                schema_name='public',
                name='Public',
                short_name='Public',
            )
            self.stdout.write(self.style.SUCCESS('Public tenant created'))
        else:
            self.stdout.write('Public tenant already exists')

        # Check if domain exists
        domain = Domain.objects.filter(domain=public_domain).first()

        if not domain:
            self.stdout.write(f'Creating domain {public_domain}...')
            Domain.objects.create(
                domain=public_domain,
                tenant=public_tenant,
                is_primary=True,
            )
            self.stdout.write(self.style.SUCCESS(f'Domain {public_domain} created'))
        else:
            self.stdout.write(f'Domain {public_domain} already exists')

        self.stdout.write(self.style.SUCCESS('Public tenant setup complete!'))
