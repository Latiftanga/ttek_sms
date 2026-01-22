"""
Management command to create demo schools for showcasing.
Creates two schools: Demo Basic School and Demo SHS.
"""
import sys
from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context

from schools.models import School, Domain
from accounts.models import User, Region, District


class Command(BaseCommand):
    help = 'Create demo schools (Basic and SHS) for testing and showcasing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Delete existing demo schools and recreate them',
        )
        parser.add_argument(
            '--domain-suffix',
            type=str,
            default='ttek-sms.com',
            help='Domain suffix for demo schools (default: ttek-sms.com)',
        )

    def handle(self, *args, **options):
        force = options['force']
        domain_suffix = options['domain_suffix']

        self.stdout.write(self.style.NOTICE('Creating demo schools...'))

        # Ensure we're in public schema
        connection.set_schema_to_public()

        # Create or get region and district
        region, _ = Region.objects.get_or_create(
            code='GA',
            defaults={'name': 'Greater Accra'}
        )
        district, _ = District.objects.get_or_create(
            name='Accra Metropolitan',
            region=region
        )

        # Define demo schools
        demo_schools = [
            {
                'name': 'Demo Basic School',
                'short_name': 'DBS',
                'schema_name': 'demo_basic',
                'domain': f'demo-basic.{domain_suffix}',
                'education_system': 'basic',
                'enabled_levels': ['creche', 'nursery', 'kg', 'primary', 'jhs'],
                'email': 'info@demobasic.edu.gh',
                'phone': '+233201234567',
                'address': '123 Education Street, Accra',
                'city': 'Accra',
                'headmaster_name': 'Mr. Kwame Asante',
                'headmaster_title': 'Headmaster',
                'admin_email': 'admin@demobasic.edu.gh',
                'admin_password': 'Demo@2024',
            },
            {
                'name': 'Demo Senior High School',
                'short_name': 'DSHS',
                'schema_name': 'demo_shs',
                'domain': f'demo-shs.{domain_suffix}',
                'education_system': 'shs',
                'enabled_levels': ['shs'],
                'email': 'info@demoshs.edu.gh',
                'phone': '+233209876543',
                'address': '456 Knowledge Avenue, Accra',
                'city': 'Accra',
                'headmaster_name': 'Dr. Ama Mensah',
                'headmaster_title': 'Headmistress',
                'admin_email': 'admin@demoshs.edu.gh',
                'admin_password': 'Demo@2024',
            },
        ]

        for school_data in demo_schools:
            self._create_school(school_data, region, district, force)

        self.stdout.write(self.style.SUCCESS('\n✓ Demo schools created successfully!'))
        self.stdout.write('\nDemo School Access:')
        self.stdout.write('-' * 50)
        for school_data in demo_schools:
            self.stdout.write(f"\n{school_data['name']}:")
            self.stdout.write(f"  URL: https://{school_data['domain']}/")
            self.stdout.write(f"  Admin: {school_data['admin_email']}")
            self.stdout.write(f"  Password: {school_data['admin_password']}")

        self.stdout.write('\n\nNext step: Run populate_demo_data to add dummy data:')
        self.stdout.write('  python manage.py populate_demo_data --schema=demo_basic')
        self.stdout.write('  python manage.py populate_demo_data --schema=demo_shs')

    def _create_school(self, school_data, region, district, force):
        schema_name = school_data['schema_name']

        # Check if school exists
        existing = School.objects.filter(schema_name=schema_name).first()
        if existing:
            if force:
                self.stdout.write(f"  Deleting existing school: {existing.name}")
                existing.delete()  # This also drops the schema
            else:
                self.stdout.write(
                    self.style.WARNING(f"  School '{school_data['name']}' already exists. Use --force to recreate.")
                )
                return

        self.stdout.write(f"\n  Creating: {school_data['name']}")

        # Create the school (tenant)
        school = School.objects.create(
            name=school_data['name'],
            short_name=school_data['short_name'],
            schema_name=schema_name,
            education_system=school_data['education_system'],
            enabled_levels=school_data['enabled_levels'],
            email=school_data['email'],
            phone=school_data['phone'],
            address=school_data['address'],
            city=school_data['city'],
            location_region=region,
            location_district=district,
            headmaster_name=school_data['headmaster_name'],
            headmaster_title=school_data['headmaster_title'],
        )

        # Create domain
        Domain.objects.create(
            domain=school_data['domain'],
            tenant=school,
            is_primary=True
        )

        self.stdout.write(f"    ✓ Tenant created: {schema_name}")
        self.stdout.write(f"    ✓ Domain: {school_data['domain']}")

        # Create school admin user within the tenant schema
        with schema_context(schema_name):
            admin_user = User.objects.create_user(
                email=school_data['admin_email'],
                password=school_data['admin_password'],
                first_name=school_data['headmaster_name'].split()[-1],
                last_name=school_data['headmaster_name'].split()[0].replace('Mr.', '').replace('Mrs.', '').replace('Dr.', '').strip(),
                is_school_admin=True,
                is_staff=True,
            )
            self.stdout.write(f"    ✓ Admin user: {school_data['admin_email']}")
