# Data migration to convert PRIMARY and JHS to BASIC

from django.db import migrations


def convert_to_basic(apps, schema_editor):
    """
    Convert PRIMARY and JHS classes to BASIC level type.
    - PRIMARY (1-6) -> BASIC (1-6)
    - JHS (1-3) -> BASIC (7-9)
    """
    Class = apps.get_model('academics', 'Class')

    # Convert PRIMARY to BASIC (level_number stays the same)
    Class.objects.filter(level_type='primary').update(level_type='basic')

    # Convert JHS to BASIC (level_number needs to be adjusted: 1->7, 2->8, 3->9)
    for cls in Class.objects.filter(level_type='jhs'):
        cls.level_type = 'basic'
        cls.level_number = cls.level_number + 6  # JHS 1 = Basic 7, JHS 2 = Basic 8, etc.
        cls.save()


def reverse_to_primary_jhs(apps, schema_editor):
    """
    Reverse: Convert BASIC back to PRIMARY or JHS.
    - BASIC (1-6) -> PRIMARY (1-6)
    - BASIC (7-9) -> JHS (1-3)
    """
    Class = apps.get_model('academics', 'Class')

    # Convert BASIC 1-6 back to PRIMARY
    Class.objects.filter(level_type='basic', level_number__lte=6).update(level_type='primary')

    # Convert BASIC 7-9 back to JHS
    for cls in Class.objects.filter(level_type='basic', level_number__gte=7):
        cls.level_type = 'jhs'
        cls.level_number = cls.level_number - 6  # Basic 7 = JHS 1, Basic 8 = JHS 2, etc.
        cls.save()


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0011_add_nursery_level_type'),
    ]

    operations = [
        migrations.RunPython(convert_to_basic, reverse_to_primary_jhs),
    ]
