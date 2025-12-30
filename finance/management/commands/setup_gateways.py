"""
Management command to set up default payment gateways.

Usage:
    python manage.py setup_gateways
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import tenant_context
from schools.models import School
from finance.models import PaymentGateway


class Command(BaseCommand):
    help = 'Set up default payment gateways for all tenants'

    def handle(self, *args, **options):
        gateways = [
            {
                'name': 'PAYSTACK',
                'display_name': 'Paystack',
                'description': 'Paystack is a leading payment gateway in Ghana and Nigeria. '
                               'Supports Mobile Money (MTN, Vodafone, AirtelTigo), Card payments, '
                               'Bank transfers, and USSD.',
                'supports_mobile_money': True,
                'supports_cards': True,
                'supports_bank_transfer': True,
                'setup_instructions': '''
1. Create a Paystack account at https://paystack.com
2. Complete your business verification
3. Navigate to Settings > API Keys & Webhooks
4. Copy your Secret Key and Public Key
5. Set up your webhook URL for payment notifications
                '''.strip(),
            },
            {
                'name': 'FLUTTERWAVE',
                'display_name': 'Flutterwave',
                'description': 'Flutterwave supports payments across Africa including Ghana. '
                               'Supports Mobile Money, Card payments, Bank transfers, and USSD.',
                'supports_mobile_money': True,
                'supports_cards': True,
                'supports_bank_transfer': True,
                'setup_instructions': '''
1. Create a Flutterwave account at https://flutterwave.com
2. Complete business verification
3. Go to Settings > API Keys
4. Copy your Secret Key and Public Key
5. Generate an encryption key for secure transactions
                '''.strip(),
            },
            {
                'name': 'HUBTEL',
                'display_name': 'Hubtel',
                'description': 'Hubtel is a Ghana-focused payment gateway. '
                               'Supports Mobile Money (MTN, Vodafone, AirtelTigo), Card payments, '
                               'and Hubtel Wallet.',
                'supports_mobile_money': True,
                'supports_cards': True,
                'supports_bank_transfer': False,
                'setup_instructions': '''
1. Create a Hubtel account at https://hubtel.com
2. Set up your merchant account
3. Go to Merchant Dashboard > API
4. Copy your Client ID and Client Secret
5. Note your Merchant Account Number
                '''.strip(),
            },
        ]

        # Get all tenants (excluding public schema)
        tenants = School.objects.exclude(schema_name='public')

        if not tenants.exists():
            self.stdout.write(
                self.style.WARNING('No tenants found. Gateways will be created when tenants are added.')
            )
            return

        for tenant in tenants:
            self.stdout.write(f'\nSetting up gateways for: {tenant.name}')

            with tenant_context(tenant):
                created_count = 0
                updated_count = 0

                for gateway_data in gateways:
                    gateway, created = PaymentGateway.objects.update_or_create(
                        name=gateway_data['name'],
                        defaults=gateway_data
                    )

                    if created:
                        created_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'  Created: {gateway.display_name}')
                        )
                    else:
                        updated_count += 1
                        self.stdout.write(
                            self.style.WARNING(f'  Updated: {gateway.display_name}')
                        )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'  Done! Created {created_count}, updated {updated_count} gateways.'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(f'\nCompleted setup for {tenants.count()} tenant(s).')
        )
