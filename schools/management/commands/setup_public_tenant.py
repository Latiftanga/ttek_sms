import os
from django.core.management.base import BaseCommand
from schools.models import School, Domain


class Command(BaseCommand):
    help = 'Create public tenant and register domain'

    def handle(self, *args, **options):
        # Get domain from environment or use default
        public_domain = os.getenv('PUBLIC_DOMAIN', 'localhost')

        self.stdout.write(f'Setting up public tenant for domain: {public_domain}')

        # List all existing tenants for debugging
        all_tenants = School.objects.all()
        self.stdout.write(f'Existing tenants: {[(t.schema_name, t.name) for t in all_tenants]}')

        # Check if public tenant exists
        public_tenant = School.objects.filter(schema_name='public').first()

        if not public_tenant:
            self.stdout.write('Creating public tenant with schema_name=public...')
            public_tenant = School.objects.create(
                schema_name='public',
                name='TTEK SMS Platform',
                short_name='TTEK',
            )
            self.stdout.write(self.style.SUCCESS('Public tenant created'))
        else:
            self.stdout.write(f'Public tenant exists: schema={public_tenant.schema_name}, name={public_tenant.name}')

        # List all domains for debugging
        all_domains = Domain.objects.all()
        self.stdout.write(f'Existing domains: {[(d.domain, d.tenant.schema_name, d.is_primary) for d in all_domains]}')

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
        elif domain.tenant.schema_name != 'public':
            self.stdout.write(f'Domain {public_domain} exists but points to {domain.tenant.schema_name}, updating...')
            domain.tenant = public_tenant
            domain.save()
            self.stdout.write(self.style.SUCCESS(f'Domain updated to point to public tenant'))
        else:
            self.stdout.write(f'Domain {public_domain} already exists for public tenant')

        self.stdout.write(self.style.SUCCESS('Public tenant setup complete!'))
