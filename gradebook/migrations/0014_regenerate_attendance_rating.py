"""
Discard teacher-chosen attendance ratings and regenerate them automatically.

Attendance used to be rated manually by class teachers. The system now
derives the rating from recorded attendance, so the old manual values are
wiped and replaced with one derived from each report's stored
attendance_percentage. Reports with no attendance data are left blank
(displayed as "-") rather than given a fabricated rating.
"""
from django.db import migrations


def derive_rating(attendance_percentage):
    if attendance_percentage is None:
        return ''
    pct = float(attendance_percentage)
    if pct >= 95:
        return 'EXCELLENT'
    elif pct >= 85:
        return 'VERY_GOOD'
    elif pct >= 75:
        return 'GOOD'
    elif pct >= 60:
        return 'FAIR'
    return 'POOR'


def regenerate_attendance_rating(apps, schema_editor):
    TermReport = apps.get_model('gradebook', 'TermReport')
    updated = 0
    for report in TermReport.objects.all().iterator():
        new_rating = derive_rating(report.attendance_percentage)
        if report.attendance_rating != new_rating:
            report.attendance_rating = new_rating
            report.save(update_fields=['attendance_rating'])
            updated += 1
    if updated:
        print(f"  Regenerated attendance rating on {updated} report(s)")


class Migration(migrations.Migration):

    dependencies = [
        ("gradebook", "0013_add_score_feedback"),
    ]

    operations = [
        # One-way data fix: the original teacher-chosen ratings cannot be
        # recovered, so there is no meaningful reverse.
        migrations.RunPython(
            regenerate_attendance_rating,
            migrations.RunPython.noop,
        ),
    ]
