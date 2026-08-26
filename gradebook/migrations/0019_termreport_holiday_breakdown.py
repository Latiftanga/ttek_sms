from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gradebook", "0018_assessmentcategory_default_max_marks_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="termreport",
            name="holiday_breakdown",
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='Snapshot of excluded-day counts by category for the term, e.g. {"Public Holiday": 5, "Weather Closure": 3}',
            ),
        ),
    ]
