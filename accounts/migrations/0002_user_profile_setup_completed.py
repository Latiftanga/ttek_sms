# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='profile_setup_completed',
            field=models.BooleanField(
                default=True,
                help_text='User has completed the profile setup wizard'
            ),
        ),
    ]
