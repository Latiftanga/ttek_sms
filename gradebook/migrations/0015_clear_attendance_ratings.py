"""
Clear every stored attendance rating on term reports.

Attendance ratings are no longer chosen manually; the system derives them
from recorded attendance during report calculation. This wipes all existing
values to blank ("-" on report cards) so nothing stale survives. The rating
is auto-populated again the next time each report's attendance is calculated.
"""
from django.db import migrations


def clear_attendance_ratings(apps, schema_editor):
    TermReport = apps.get_model('gradebook', 'TermReport')
    updated = TermReport.objects.exclude(attendance_rating='').update(
        attendance_rating=''
    )
    if updated:
        print(f"  Cleared attendance rating on {updated} report(s)")


class Migration(migrations.Migration):

    dependencies = [
        ("gradebook", "0014_regenerate_attendance_rating"),
    ]

    operations = [
        # One-way data wipe: prior ratings are intentionally discarded and
        # cannot be reconstructed, so there is no meaningful reverse.
        migrations.RunPython(
            clear_attendance_ratings,
            migrations.RunPython.noop,
        ),
    ]
