from django.core.management.base import BaseCommand
from django.db import connection
from schools.models import School, Domain

class Command(BaseCommand):
    help = 'Setup localhost tenant for development'

    def handle(self, *args, **options):
        # Drop existing tables to fix schema mismatch
        with connection.cursor() as cursor:
            self.stdout.write('Dropping existing tables...')
            cursor.execute('DROP TABLE IF EXISTS schools_domain CASCADE')
            cursor.execute('DROP TABLE IF EXISTS schools_school CASCADE')
            self.stdout.write(self.style.SUCCESS('✓ Tables dropped'))
        
        # Recreate tables with correct schema
        from django.core.management import call_command
        self.stdout.write('Running migrations...')
        call_command('migrate', 'schools', '--run-syncdb', verbosity=0)
        self.stdout.write(self.style.SUCCESS('✓ Tables recreated'))
        
        # Create the school tenant
        school, created = School.objects.get_or_create(
            schema_name='public',
            defaults={
                'name': 'Localhost Development',
                'short_name': 'Localhost',
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ Localhost school created (ID: {school.id})'))
        else:
            self.stdout.write(self.style.WARNING('Localhost school already exists'))
        
        # Create the domain for this tenant
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
        
        self.stdout.write(self.style.SUCCESS('\n✓ Setup complete! You can now access the app at http://localhost'))