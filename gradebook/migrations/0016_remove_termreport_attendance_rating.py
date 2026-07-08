"""
Remove the stored attendance_rating field from TermReport.

The rating is now computed as a @property from attendance_percentage, so
the database column is no longer needed. This removes all stale stored
values that were causing production errors.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("gradebook", "0015_clear_attendance_ratings"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="termreport",
            name="attendance_rating",
        ),
    ]
