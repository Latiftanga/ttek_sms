from django.db import migrations, models
from django.utils import timezone


def populate_null_dates(apps, schema_editor):
    """Set any null dates to today's date before making field required."""
    Assignment = apps.get_model('gradebook', 'Assignment')
    Assignment.objects.filter(date__isnull=True).update(date=timezone.now().date())


def reverse_populate(apps, schema_editor):
    """No-op for reverse migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('gradebook', '0005_add_category_scores_json'),
    ]

    operations = [
        # First, populate any null dates
        migrations.RunPython(populate_null_dates, reverse_populate),
        # Then alter the field to be non-nullable
        migrations.AlterField(
            model_name='assignment',
            name='date',
            field=models.DateField(help_text='Date the assignment was administered'),
        ),
    ]
