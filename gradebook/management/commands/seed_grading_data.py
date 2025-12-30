"""
Management command to seed default Ghana grading systems and assessment categories.
This creates the standard WAEC grading scale used in Ghana for Basic and SHS schools.

Usage:
    # Run for a specific tenant
    python manage.py tenant_command seed_grading_data --schema=demo

    # Or run for all tenants
    python manage.py tenant_command seed_grading_data --all
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django_tenants.utils import schema_context

from gradebook.models import GradingSystem, GradeScale, AssessmentCategory


class Command(BaseCommand):
    help = 'Seed default Ghana grading systems (BECE/WASSCE) and assessment categories'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing grading data',
        )
        parser.add_argument(
            '--schema',
            type=str,
            help='Tenant schema name to run this command for',
        )

    def handle(self, *args, **options):
        force = options['force']
        schema = options.get('schema')

        if schema:
            # Run within specific tenant context
            with schema_context(schema):
                self._seed_data(force)
        else:
            # Try to run in current context (works if called via tenant_command)
            self._seed_data(force)

    def _seed_data(self, force):
        """Seed the grading data."""
        with transaction.atomic():
            self.create_assessment_categories(force)
            self.create_basic_grading_system(force)
            self.create_shs_grading_system(force)

        self.stdout.write(self.style.SUCCESS('Successfully seeded grading data'))

    def create_assessment_categories(self, force):
        """Create Ghana SBA assessment categories (30% CA + 70% Exam)."""
        if AssessmentCategory.objects.exists() and not force:
            self.stdout.write('Assessment categories already exist. Use --force to overwrite.')
            return

        if force:
            AssessmentCategory.objects.all().delete()

        categories = [
            {
                'name': 'Class Score',
                'short_name': 'CA',
                'category_type': 'CLASS_SCORE',
                'percentage': 30,
                'order': 1,
            },
            {
                'name': 'Examination',
                'short_name': 'EXAM',
                'category_type': 'EXAM',
                'percentage': 70,
                'order': 2,
            },
        ]

        for cat_data in categories:
            AssessmentCategory.objects.create(**cat_data)
            self.stdout.write(f'  Created category: {cat_data["name"]} ({cat_data["percentage"]}%)')

        self.stdout.write(self.style.SUCCESS('Created assessment categories'))

    def create_basic_grading_system(self, force):
        """Create BECE grading system for Basic schools."""
        if GradingSystem.objects.filter(level='BASIC').exists() and not force:
            self.stdout.write('BASIC grading system already exists. Use --force to overwrite.')
            return

        if force:
            GradingSystem.objects.filter(level='BASIC').delete()

        system = GradingSystem.objects.create(
            name='BECE Standard',
            level='BASIC',
            description='Basic Education Certificate Examination grading scale used in Ghana for JHS',
            is_active=True,
            pass_mark=40,
            credit_mark=50,
            aggregate_subjects_count=6,
            min_subjects_to_pass=4,
            min_average_for_promotion=40,
            require_core_pass=True,
        )

        # BECE grading scale (same as WASSCE but typically used 1-9)
        scales = [
            {'grade_label': '1', 'min': 80, 'max': 100, 'points': 1, 'interpretation': 'Excellent', 'is_pass': True, 'is_credit': True},
            {'grade_label': '2', 'min': 70, 'max': 79, 'points': 2, 'interpretation': 'Very Good', 'is_pass': True, 'is_credit': True},
            {'grade_label': '3', 'min': 65, 'max': 69, 'points': 3, 'interpretation': 'Good', 'is_pass': True, 'is_credit': True},
            {'grade_label': '4', 'min': 60, 'max': 64, 'points': 4, 'interpretation': 'Credit', 'is_pass': True, 'is_credit': True},
            {'grade_label': '5', 'min': 55, 'max': 59, 'points': 5, 'interpretation': 'Credit', 'is_pass': True, 'is_credit': True},
            {'grade_label': '6', 'min': 50, 'max': 54, 'points': 6, 'interpretation': 'Credit', 'is_pass': True, 'is_credit': True},
            {'grade_label': '7', 'min': 45, 'max': 49, 'points': 7, 'interpretation': 'Pass', 'is_pass': True, 'is_credit': False},
            {'grade_label': '8', 'min': 40, 'max': 44, 'points': 8, 'interpretation': 'Pass', 'is_pass': True, 'is_credit': False},
            {'grade_label': '9', 'min': 0, 'max': 39, 'points': 9, 'interpretation': 'Fail', 'is_pass': False, 'is_credit': False},
        ]

        for i, scale_data in enumerate(scales):
            GradeScale.objects.create(
                grading_system=system,
                grade_label=scale_data['grade_label'],
                min_percentage=scale_data['min'],
                max_percentage=scale_data['max'],
                aggregate_points=scale_data['points'],
                interpretation=scale_data['interpretation'],
                is_pass=scale_data['is_pass'],
                is_credit=scale_data['is_credit'],
                order=i,
            )

        self.stdout.write(self.style.SUCCESS(f'Created BECE grading system with {len(scales)} grades'))

    def create_shs_grading_system(self, force):
        """Create WASSCE grading system for SHS."""
        if GradingSystem.objects.filter(level='SHS').exists() and not force:
            self.stdout.write('SHS grading system already exists. Use --force to overwrite.')
            return

        if force:
            GradingSystem.objects.filter(level='SHS').delete()

        system = GradingSystem.objects.create(
            name='WASSCE Standard',
            level='SHS',
            description='West African Senior School Certificate Examination grading scale',
            is_active=True,
            pass_mark=40,
            credit_mark=50,
            aggregate_subjects_count=6,
            min_subjects_to_pass=6,
            min_average_for_promotion=40,
            require_core_pass=True,
        )

        # WASSCE grading scale (A1-F9)
        scales = [
            {'grade_label': 'A1', 'min': 80, 'max': 100, 'points': 1, 'interpretation': 'Excellent', 'is_pass': True, 'is_credit': True},
            {'grade_label': 'B2', 'min': 70, 'max': 79, 'points': 2, 'interpretation': 'Very Good', 'is_pass': True, 'is_credit': True},
            {'grade_label': 'B3', 'min': 65, 'max': 69, 'points': 3, 'interpretation': 'Good', 'is_pass': True, 'is_credit': True},
            {'grade_label': 'C4', 'min': 60, 'max': 64, 'points': 4, 'interpretation': 'Credit', 'is_pass': True, 'is_credit': True},
            {'grade_label': 'C5', 'min': 55, 'max': 59, 'points': 5, 'interpretation': 'Credit', 'is_pass': True, 'is_credit': True},
            {'grade_label': 'C6', 'min': 50, 'max': 54, 'points': 6, 'interpretation': 'Credit', 'is_pass': True, 'is_credit': True},
            {'grade_label': 'D7', 'min': 45, 'max': 49, 'points': 7, 'interpretation': 'Pass', 'is_pass': True, 'is_credit': False},
            {'grade_label': 'E8', 'min': 40, 'max': 44, 'points': 8, 'interpretation': 'Pass', 'is_pass': True, 'is_credit': False},
            {'grade_label': 'F9', 'min': 0, 'max': 39, 'points': 9, 'interpretation': 'Fail', 'is_pass': False, 'is_credit': False},
        ]

        for i, scale_data in enumerate(scales):
            GradeScale.objects.create(
                grading_system=system,
                grade_label=scale_data['grade_label'],
                min_percentage=scale_data['min'],
                max_percentage=scale_data['max'],
                aggregate_points=scale_data['points'],
                interpretation=scale_data['interpretation'],
                is_pass=scale_data['is_pass'],
                is_credit=scale_data['is_credit'],
                order=i,
            )

        self.stdout.write(self.style.SUCCESS(f'Created WASSCE grading system with {len(scales)} grades'))
