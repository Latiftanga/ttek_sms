from django.db import migrations, models
import django.db.models.deletion


def backfill_public_holiday(apps, schema_editor):
    SchoolHoliday = apps.get_model('core', 'SchoolHoliday')
    HolidayCategory = apps.get_model('core', 'HolidayCategory')
    public_holiday, _ = HolidayCategory.objects.get_or_create(name='Public Holiday')
    SchoolHoliday.objects.filter(category__isnull=True).update(category=public_holiday)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0028_schoolholiday_category_nullable"),
    ]

    operations = [
        migrations.RunPython(backfill_public_holiday, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="schoolholiday",
            name="category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="holidays",
                to="core.holidaycategory",
                help_text="Why attendance isn't taken this day - shown as a breakdown on report cards.",
            ),
        ),
    ]
