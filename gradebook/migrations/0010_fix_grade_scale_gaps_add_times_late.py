"""
Fix grade scale boundary gaps and add times_late field.

Grade scales used integer max boundaries (e.g., B2: 70-79), but scores are
DecimalField(decimal_places=2). A score of 79.50 falls in a gap — matches
neither <= 79 nor >= 80 — so the student gets NO GRADE. This migration
updates all max_percentage values that are integer boundaries to .99
(e.g., 79 → 79.99), except 100 which stays as the top boundary.
"""
from decimal import Decimal

from django.db import migrations, models


# Boundaries to fix: integer max values that create gaps (exclude 100)
BOUNDARY_FIXES = {
    Decimal('39'): Decimal('39.99'),
    Decimal('44'): Decimal('44.99'),
    Decimal('49'): Decimal('49.99'),
    Decimal('54'): Decimal('54.99'),
    Decimal('59'): Decimal('59.99'),
    Decimal('64'): Decimal('64.99'),
    Decimal('69'): Decimal('69.99'),
    Decimal('79'): Decimal('79.99'),
}


def fix_grade_scale_gaps(apps, schema_editor):
    GradeScale = apps.get_model('gradebook', 'GradeScale')
    for old_max, new_max in BOUNDARY_FIXES.items():
        updated = GradeScale.objects.filter(max_percentage=old_max).update(
            max_percentage=new_max
        )
        if updated:
            print(f"  Updated {updated} grade scale(s): max {old_max} → {new_max}")


def reverse_grade_scale_gaps(apps, schema_editor):
    GradeScale = apps.get_model('gradebook', 'GradeScale')
    for old_max, new_max in BOUNDARY_FIXES.items():
        GradeScale.objects.filter(max_percentage=new_max).update(
            max_percentage=old_max
        )


class Migration(migrations.Migration):

    dependencies = [
        ("gradebook", "0009_alter_termreport_attendance_rating"),
    ]

    operations = [
        # Fix grade scale boundary gaps
        migrations.RunPython(
            fix_grade_scale_gaps,
            reverse_grade_scale_gaps,
        ),
        # Add times_late field to TermReport
        migrations.AddField(
            model_name="termreport",
            name="times_late",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Number of times student was late in the term",
                null=True,
            ),
        ),
    ]
