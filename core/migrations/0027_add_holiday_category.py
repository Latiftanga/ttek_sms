from django.db import migrations, models
import django.db.models.deletion


def seed_default_categories(apps, schema_editor):
    HolidayCategory = apps.get_model('core', 'HolidayCategory')
    for name in ('Public Holiday', 'Weather Closure'):
        HolidayCategory.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0026_term_head_teacher_message"),
    ]

    operations = [
        migrations.CreateModel(
            name="HolidayCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=50, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Holiday Category",
                "verbose_name_plural": "Holiday Categories",
                "ordering": ["name"],
            },
        ),
        migrations.RunPython(seed_default_categories, migrations.RunPython.noop),
    ]
