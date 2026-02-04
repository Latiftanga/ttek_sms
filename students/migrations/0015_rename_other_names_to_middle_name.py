# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0014_add_exeat_sms_tracking'),
    ]

    operations = [
        migrations.RenameField(
            model_name='student',
            old_name='other_names',
            new_name='middle_name',
        ),
    ]
