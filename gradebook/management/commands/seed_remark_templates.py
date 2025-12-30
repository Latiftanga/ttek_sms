"""
Management command to seed default remark templates.
Usage: python manage.py seed_remark_templates
"""
from django.core.management.base import BaseCommand
from django_tenants.utils import get_tenant_model, tenant_context

from gradebook.models import RemarkTemplate


DEFAULT_TEMPLATES = [
    # Excellent (80%+)
    {
        'category': 'EXCELLENT',
        'content': 'An outstanding performance! Keep up the excellent work.',
        'order': 1,
    },
    {
        'category': 'EXCELLENT',
        'content': '{student_name} has shown exceptional dedication and achieved remarkable results. Keep it up!',
        'order': 2,
    },
    {
        'category': 'EXCELLENT',
        'content': 'Excellent academic performance. A role model for others.',
        'order': 3,
    },

    # Good (60-79%)
    {
        'category': 'GOOD',
        'content': 'Good effort this term. With continued dedication, even better results are achievable.',
        'order': 1,
    },
    {
        'category': 'GOOD',
        'content': 'A commendable performance. Keep working hard!',
        'order': 2,
    },
    {
        'category': 'GOOD',
        'content': '{student_name} shows great potential and is making good progress.',
        'order': 3,
    },

    # Average (50-59%)
    {
        'category': 'AVERAGE',
        'content': 'A fair performance. More effort and focus is needed to improve.',
        'order': 1,
    },
    {
        'category': 'AVERAGE',
        'content': 'Shows potential but needs to apply more effort in studies.',
        'order': 2,
    },
    {
        'category': 'AVERAGE',
        'content': 'Can do better with more concentration and regular revision.',
        'order': 3,
    },

    # Needs Improvement (<50%)
    {
        'category': 'NEEDS_IMPROVEMENT',
        'content': 'Performance is below expectation. Requires significant improvement and parental support.',
        'order': 1,
    },
    {
        'category': 'NEEDS_IMPROVEMENT',
        'content': 'Needs to pay more attention in class and complete assignments on time.',
        'order': 2,
    },
    {
        'category': 'NEEDS_IMPROVEMENT',
        'content': 'Must put in more effort. Extra coaching may be beneficial.',
        'order': 3,
    },

    # General
    {
        'category': 'GENERAL',
        'content': 'Respectful and well-behaved student.',
        'order': 1,
    },
    {
        'category': 'GENERAL',
        'content': 'Participates actively in class activities.',
        'order': 2,
    },
    {
        'category': 'GENERAL',
        'content': 'Shows leadership qualities.',
        'order': 3,
    },
    {
        'category': 'GENERAL',
        'content': 'A pleasure to teach.',
        'order': 4,
    },
]


class Command(BaseCommand):
    help = 'Seed default remark templates for all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant',
            type=str,
            help='Specific tenant schema name to seed (optional)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing templates before seeding',
        )

    def handle(self, *args, **options):
        TenantModel = get_tenant_model()
        tenant_name = options.get('tenant')
        clear = options.get('clear', False)

        if tenant_name:
            try:
                tenant = TenantModel.objects.get(schema_name=tenant_name)
                tenants = [tenant]
            except TenantModel.DoesNotExist:
                self.stderr.write(f"Tenant '{tenant_name}' not found.")
                return
        else:
            # Get all tenants except public schema
            tenants = TenantModel.objects.exclude(schema_name='public')

        for tenant in tenants:
            with tenant_context(tenant):
                self.seed_templates(tenant, clear)

    def seed_templates(self, tenant, clear=False):
        if clear:
            count = RemarkTemplate.objects.all().delete()[0]
            self.stdout.write(f"  Cleared {count} existing templates")

        created_count = 0
        for template_data in DEFAULT_TEMPLATES:
            obj, created = RemarkTemplate.objects.get_or_create(
                category=template_data['category'],
                content=template_data['content'],
                defaults={'order': template_data['order']}
            )
            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"[{tenant.schema_name}] Created {created_count} templates"
            )
        )
