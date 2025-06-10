# core/management/commands/test_system.py
from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.auth import get_user_model
from core.models import School

User = get_user_model()


class Command(BaseCommand):
    help = 'Test system setup and display access information'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-test-data',
            action='store_true',
            help='Create test school and superuser',
        )

    def handle(self, *args, **options):
        if options['create_test_data']:
            self.create_test_data()

        self.display_system_info()

    def create_test_data(self):
        """Create test data for the system"""
        self.stdout.write(self.style.WARNING('Creating test data...'))

        # Create superuser if doesn't exist
        if not User.objects.filter(is_superuser=True).exists():
            superuser = User.objects.create_superuser(
                username='admin',
                email='admin@ttek.com',
                password='admin123'
            )
            self.stdout.write(
                self.style.SUCCESS(f'✅ Created superuser: admin/admin123')
            )

        # Create test school if doesn't exist
        if not School.objects.filter(name='Test High School').exists():
            school = School.objects.create(
                name='Test High School',
                subdomain='test',
                description='A test school for development',
                email='info@testschool.edu',
                phone='+233-123-456-789',
                is_active=True
            )
            self.stdout.write(
                self.style.SUCCESS(f'✅ Created test school: {school.name}')
            )

    def display_system_info(self):
        """Display system information and access methods"""
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('🚀 TTEK SMS System Information'))
        self.stdout.write('=' * 50)

        # System stats
        total_schools = School.objects.count()
        active_schools = School.objects.filter(is_active=True).count()
        superusers = User.objects.filter(is_superuser=True).count()

        self.stdout.write(f'📊 System Stats:')
        self.stdout.write(f'   • Total Schools: {total_schools}')
        self.stdout.write(f'   • Active Schools: {active_schools}')
        self.stdout.write(f'   • Superusers: {superusers}')
        self.stdout.write('')

        # Developer access
        self.stdout.write(self.style.WARNING('🔧 Developer Access:'))
        self.stdout.write(f'   • Portal: http://localhost:8000/')
        self.stdout.write(
            f'   • System Overview: http://localhost:8000/system/')
        self.stdout.write(f'   • Django Admin: http://localhost:8000/admin/')
        self.stdout.write('')

        # Schools
        schools = School.objects.filter(is_active=True)
        if schools.exists():
            self.stdout.write(self.style.WARNING('🏫 School Access:'))
            for school in schools:
                self.stdout.write(f'   📚 {school.name} (ID: {school.id})')

                # Production URLs
                if school.domain:
                    self.stdout.write(
                        f'      🌐 Custom Domain: https://{school.domain}/')
                elif school.subdomain:
                    main_domain = getattr(settings, 'MAIN_DOMAIN', 'ttek.com')
                    self.stdout.write(
                        f'      🌐 Subdomain: https://{school.subdomain}.{main_domain}/')
                else:
                    self.stdout.write(f'      ⚠️  No domain configured')

                # Development URL
                self.stdout.write(
                    f'      🛠️  Dev Login: http://localhost:8000/login/?school={school.id}')
                self.stdout.write('')
        else:
            self.stdout.write(self.style.WARNING('❌ No schools found!'))
            self.stdout.write(
                '   Run with --create-test-data to create sample data')
            self.stdout.write('')

        # Next steps
        self.stdout.write(self.style.SUCCESS('🎯 Next Steps:'))
        if not schools.exists():
            self.stdout.write(
                '   1. Run: python manage.py test_system --create-test-data')
            self.stdout.write('   2. Go to: http://localhost:8000/')
        else:
            self.stdout.write(
                '   1. Access developer portal: http://localhost:8000/')
            self.stdout.write('   2. Add more schools via Django Admin')
            self.stdout.write('   3. Configure domains for schools')
        self.stdout.write('')

        # Tips
        self.stdout.write(self.style.SUCCESS('💡 Tips:'))
        self.stdout.write('   • Use Django Admin to manage schools and users')
        self.stdout.write(
            '   • Each school needs either a domain OR subdomain')
        self.stdout.write('   • Test school login with the dev URLs above')
        self.stdout.write('   • System overview shows comprehensive analytics')
        self.stdout.write('')
