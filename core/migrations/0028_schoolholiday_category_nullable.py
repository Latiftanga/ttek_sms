from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0027_add_holiday_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="schoolholiday",
            name="category",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="holidays",
                to="core.holidaycategory",
                help_text="Why attendance isn't taken this day - shown as a breakdown on report cards.",
            ),
        ),
    ]
