# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0015_rename_other_names_to_middle_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='residence_type',
            field=models.CharField(
                blank=True,
                choices=[('day', 'Day'), ('boarding', 'Boarding')],
                default='',
                help_text='Day or Boarding student',
                max_length=10,
            ),
        ),
    ]
