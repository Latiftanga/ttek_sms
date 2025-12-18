from django.core.management.base import BaseCommand
from schools.models import School, Domain

class Command(BaseCommand):
    help = 'Setup localhost tenant for development'

    def handle(self, *args, **options):
        # Create or get the school tenant
        school, created = School.objects.get_or_create(
            schema_name='public',
            defaults={
                'name': 'Localhost Development',
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS('✓ Localhost school created'))
        else:
            self.stdout.write(self.style.WARNING('Localhost school already exists'))
        
        # Create or get the domain for this tenant
        domain, domain_created = Domain.objects.get_or_create(
            domain='localhost',
            defaults={
                'tenant': school,
                'is_primary': True,
            }
        )
        
        if domain_created:
            self.stdout.write(self.style.SUCCESS('✓ Localhost domain created'))
        else:
            self.stdout.write(self.style.WARNING('Localhost domain already exists'))