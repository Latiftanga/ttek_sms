"""
Management command to seed academic data: Programmes, Periods, and Subjects.
Based on Ghana Education Service curriculum.

Usage:
    # Run for a specific tenant
    python manage.py tenant_command seed_academics --schema=demo

    # With specific options
    python manage.py tenant_command seed_academics --schema=demo --periods --subjects

    # Force overwrite existing data
    python manage.py tenant_command seed_academics --schema=demo --force
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django_tenants.utils import schema_context
from datetime import time

from academics.models import Programme, Period, Subject


class Command(BaseCommand):
    help = 'Seed academic data: Programmes, Periods, and Subjects (Ghana curriculum)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing data',
        )
        parser.add_argument(
            '--schema',
            type=str,
            help='Tenant schema name to run this command for',
        )
        parser.add_argument(
            '--programmes',
            action='store_true',
            help='Seed only programmes',
        )
        parser.add_argument(
            '--periods',
            action='store_true',
            help='Seed only periods',
        )
        parser.add_argument(
            '--subjects',
            action='store_true',
            help='Seed only subjects',
        )

    def handle(self, *args, **options):
        force = options['force']
        schema = options.get('schema')

        # If no specific option, seed all
        seed_all = not (options['programmes'] or options['periods'] or options['subjects'])

        if schema:
            with schema_context(schema):
                self._seed_data(force, options, seed_all)
        else:
            self._seed_data(force, options, seed_all)

    def _seed_data(self, force, options, seed_all):
        """Seed the academic data."""
        with transaction.atomic():
            if seed_all or options['programmes']:
                self.create_programmes(force)
            if seed_all or options['periods']:
                self.create_periods(force)
            if seed_all or options['subjects']:
                self.create_subjects(force)

        self.stdout.write(self.style.SUCCESS('Successfully seeded academic data'))

    def create_programmes(self, force):
        """Create SHS programmes."""
        if Programme.objects.exists() and not force:
            self.stdout.write('Programmes already exist. Use --force to overwrite.')
            return

        if force:
            Programme.objects.all().delete()

        programmes = [
            {'name': 'General Arts', 'code': 'ART', 'description': 'Focus on humanities, languages, and social sciences'},
            {'name': 'General Science', 'code': 'SCI', 'description': 'Focus on physics, chemistry, biology, and mathematics'},
            {'name': 'Business', 'code': 'BUS', 'description': 'Focus on accounting, economics, and business management'},
            {'name': 'Visual Arts', 'code': 'VIS', 'description': 'Focus on graphic design, sculpture, and textiles'},
            {'name': 'Home Economics', 'code': 'HEC', 'description': 'Focus on food and nutrition, clothing, and management'},
            {'name': 'Agricultural Science', 'code': 'AGR', 'description': 'Focus on crop science, animal husbandry, and agribusiness'},
            {'name': 'Technical', 'code': 'TEC', 'description': 'Focus on technical drawing, woodwork, and metalwork'},
        ]

        for prog_data in programmes:
            Programme.objects.create(**prog_data)
            self.stdout.write(f'  Created programme: {prog_data["name"]} ({prog_data["code"]})')

        self.stdout.write(self.style.SUCCESS(f'Created {len(programmes)} programmes'))

    def create_periods(self, force):
        """Create standard school periods/timetable slots."""
        if Period.objects.exists() and not force:
            self.stdout.write('Periods already exist. Use --force to overwrite.')
            return

        if force:
            Period.objects.all().delete()

        periods = [
            {'name': 'Assembly', 'start_time': time(7, 30), 'end_time': time(8, 0), 'order': 1, 'is_break': True},
            {'name': 'Period 1', 'start_time': time(8, 0), 'end_time': time(8, 40), 'order': 2, 'is_break': False},
            {'name': 'Period 2', 'start_time': time(8, 40), 'end_time': time(9, 20), 'order': 3, 'is_break': False},
            {'name': 'Period 3', 'start_time': time(9, 20), 'end_time': time(10, 0), 'order': 4, 'is_break': False},
            {'name': 'Break', 'start_time': time(10, 0), 'end_time': time(10, 30), 'order': 5, 'is_break': True},
            {'name': 'Period 4', 'start_time': time(10, 30), 'end_time': time(11, 10), 'order': 6, 'is_break': False},
            {'name': 'Period 5', 'start_time': time(11, 10), 'end_time': time(11, 50), 'order': 7, 'is_break': False},
            {'name': 'Period 6', 'start_time': time(11, 50), 'end_time': time(12, 30), 'order': 8, 'is_break': False},
            {'name': 'Lunch', 'start_time': time(12, 30), 'end_time': time(13, 30), 'order': 9, 'is_break': True},
            {'name': 'Period 7', 'start_time': time(13, 30), 'end_time': time(14, 10), 'order': 10, 'is_break': False},
            {'name': 'Period 8', 'start_time': time(14, 10), 'end_time': time(14, 50), 'order': 11, 'is_break': False},
        ]

        for period_data in periods:
            Period.objects.create(**period_data)
            break_label = ' (Break)' if period_data['is_break'] else ''
            self.stdout.write(
                f'  Created: {period_data["name"]} '
                f'({period_data["start_time"].strftime("%H:%M")} - {period_data["end_time"].strftime("%H:%M")}){break_label}'
            )

        self.stdout.write(self.style.SUCCESS(f'Created {len(periods)} periods'))

    def create_subjects(self, force):
        """Create Ghana curriculum subjects."""
        if Subject.objects.exists() and not force:
            self.stdout.write('Subjects already exist. Use --force to overwrite.')
            return

        if force:
            Subject.objects.all().delete()

        # Core subjects (for all levels)
        core_subjects = [
            {'name': 'English Language', 'short_name': 'ENG', 'is_core': True},
            {'name': 'Mathematics', 'short_name': 'MATH', 'is_core': True},
            {'name': 'Integrated Science', 'short_name': 'INT SCI', 'is_core': True},
            {'name': 'Social Studies', 'short_name': 'SOC STD', 'is_core': True},
            {'name': 'Information & Communication Technology', 'short_name': 'ICT', 'is_core': True},
        ]

        # Basic/JHS subjects
        basic_subjects = [
            {'name': 'Ghanaian Language (Akan/Twi)', 'short_name': 'TWI', 'is_core': False},
            {'name': 'Ghanaian Language (Ga)', 'short_name': 'GA', 'is_core': False},
            {'name': 'Ghanaian Language (Ewe)', 'short_name': 'EWE', 'is_core': False},
            {'name': 'French', 'short_name': 'FRE', 'is_core': False},
            {'name': 'Religious and Moral Education', 'short_name': 'RME', 'is_core': False},
            {'name': 'Creative Arts', 'short_name': 'C.ARTS', 'is_core': False},
            {'name': 'Basic Design and Technology', 'short_name': 'BDT', 'is_core': False},
            {'name': 'Physical Education', 'short_name': 'PE', 'is_core': False},
            {'name': 'Career Technology', 'short_name': 'CT', 'is_core': False},
        ]

        # SHS elective subjects (by programme)
        shs_subjects = [
            # Science electives
            {'name': 'Physics', 'short_name': 'PHY', 'is_core': False},
            {'name': 'Chemistry', 'short_name': 'CHEM', 'is_core': False},
            {'name': 'Biology', 'short_name': 'BIO', 'is_core': False},
            {'name': 'Elective Mathematics', 'short_name': 'E.MATH', 'is_core': False},
            {'name': 'Further Mathematics', 'short_name': 'F.MATH', 'is_core': False},
            {'name': 'Elective ICT', 'short_name': 'E.ICT', 'is_core': False},
            {'name': 'Computing', 'short_name': 'COMP', 'is_core': False},

            # Arts electives
            {'name': 'Literature in English', 'short_name': 'LIT', 'is_core': False},
            {'name': 'Government', 'short_name': 'GOV', 'is_core': False},
            {'name': 'History', 'short_name': 'HIST', 'is_core': False},
            {'name': 'Economics', 'short_name': 'ECON', 'is_core': False},
            {'name': 'Geography', 'short_name': 'GEO', 'is_core': False},
            {'name': 'Christian Religious Studies', 'short_name': 'CRS', 'is_core': False},
            {'name': 'Islamic Religious Studies', 'short_name': 'IRS', 'is_core': False},

            # Business electives
            {'name': 'Financial Accounting', 'short_name': 'F.ACC', 'is_core': False},
            {'name': 'Cost Accounting', 'short_name': 'C.ACC', 'is_core': False},
            {'name': 'Business Management', 'short_name': 'BM', 'is_core': False},
            {'name': 'Principles of Costing', 'short_name': 'POC', 'is_core': False},

            # Visual Arts electives
            {'name': 'Graphic Design', 'short_name': 'GD', 'is_core': False},
            {'name': 'Picture Making', 'short_name': 'PM', 'is_core': False},
            {'name': 'Sculpture', 'short_name': 'SCULP', 'is_core': False},
            {'name': 'Textiles', 'short_name': 'TEX', 'is_core': False},
            {'name': 'Ceramics', 'short_name': 'CER', 'is_core': False},
            {'name': 'Leatherwork', 'short_name': 'LW', 'is_core': False},

            # Home Economics electives
            {'name': 'Food and Nutrition', 'short_name': 'F&N', 'is_core': False},
            {'name': 'Clothing and Textiles', 'short_name': 'C&T', 'is_core': False},
            {'name': 'Management in Living', 'short_name': 'MIL', 'is_core': False},
            {'name': 'General Knowledge in Art', 'short_name': 'GKA', 'is_core': False},

            # Agricultural Science electives
            {'name': 'General Agriculture', 'short_name': 'G.AGR', 'is_core': False},
            {'name': 'Animal Husbandry', 'short_name': 'AH', 'is_core': False},
            {'name': 'Crop Husbandry and Horticulture', 'short_name': 'CHH', 'is_core': False},
            {'name': 'Fisheries', 'short_name': 'FISH', 'is_core': False},

            # Technical electives
            {'name': 'Technical Drawing', 'short_name': 'TD', 'is_core': False},
            {'name': 'Building Construction', 'short_name': 'BC', 'is_core': False},
            {'name': 'Woodwork', 'short_name': 'WW', 'is_core': False},
            {'name': 'Metalwork', 'short_name': 'MW', 'is_core': False},
            {'name': 'Auto Mechanics', 'short_name': 'AM', 'is_core': False},
            {'name': 'Electronics', 'short_name': 'ELEC', 'is_core': False},
            {'name': 'Applied Electricity', 'short_name': 'AE', 'is_core': False},
        ]

        all_subjects = core_subjects + basic_subjects + shs_subjects

        for subj_data in all_subjects:
            Subject.objects.create(**subj_data)
            core_label = ' (Core)' if subj_data['is_core'] else ''
            self.stdout.write(f'  Created: {subj_data["name"]} [{subj_data["short_name"]}]{core_label}')

        self.stdout.write(self.style.SUCCESS(f'Created {len(all_subjects)} subjects'))
