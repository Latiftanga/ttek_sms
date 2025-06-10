from django.core.management.base import BaseCommand
from core.models import School


class Command(BaseCommand):
    help = 'List all schools with their domain information'

    def handle(self, *args, **options):
        schools = School.objects.all()

        if not schools.exists():
            self.stdout.write(
                self.style.WARNING(
                    'No schools found. Create one with: python manage.py setup_school --name "Your School"')
            )
            return

        self.stdout.write(
            self.style.SUCCESS('📋 School Information:')
        )
        self.stdout.write('=' * 80)

        for school in schools:
            self.stdout.write(f"\n🏫 {school.name}")
            self.stdout.write(f"   Code: {school.code}")
            self.stdout.write(f"   Subdomain: {school.subdomain}")
            self.stdout.write(f"   Domain: {school.domain or 'None'}")
            self.stdout.write(f"   Full URL: {school.get_tenant_domain}")
            self.stdout.write(f"   Login URL: {school.get_login_url}")
            self.stdout.write(
                f"   Status: {'✅ Active' if school.is_active else '❌ Inactive'}")

            # Count users
            students = school.students.filter(is_active=True).count()
            teachers = school.teachers.filter(is_active=True).count()
            self.stdout.write(
                f"   👥 Students: {students} | Teachers: {teachers}")

        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(
            self.style.SUCCESS(f'Total schools: {schools.count()}')
        )
