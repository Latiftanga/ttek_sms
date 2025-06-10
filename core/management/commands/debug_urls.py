# core/management/commands/debug_urls.py
from django.core.management.base import BaseCommand
from django.urls import reverse, NoReverseMatch


class Command(BaseCommand):
    help = 'Debug URL configuration'

    def handle(self, *args, **options):
        urls_to_check = [
            'home',
            'developer_portal',
            'system_overview',
            'login',
            'logout',
            'dashboard',
            'setup'
        ]

        self.stdout.write(self.style.SUCCESS('🔍 Checking URL Configuration:'))
        self.stdout.write('=' * 40)

        for url_name in urls_to_check:
            try:
                url_path = reverse(url_name)
                self.stdout.write(f'✅ {url_name:20} -> {url_path}')
            except NoReverseMatch:
                self.stdout.write(f'❌ {url_name:20} -> NOT FOUND')

        self.stdout.write('')
        self.stdout.write(
            'If any URLs show "NOT FOUND", check your core/urls.py configuration.')

        # Also check if middleware is working
        from django.conf import settings
        middleware_list = settings.MIDDLEWARE
        tenant_middleware = 'core.middleware.TenantMiddleware'

        if tenant_middleware in middleware_list:
            self.stdout.write(f'✅ TenantMiddleware is installed')
        else:
            self.stdout.write(f'❌ TenantMiddleware NOT found in MIDDLEWARE')
            self.stdout.write(
                f'   Add "{tenant_middleware}" to your MIDDLEWARE setting')

        # Check if core app is installed
        if 'core' in settings.INSTALLED_APPS:
            self.stdout.write(f'✅ Core app is installed')
        else:
            self.stdout.write(f'❌ Core app NOT found in INSTALLED_APPS')
