from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add missing database indexes for improved query performance.

    These indexes optimize:
    - Teacher email lookups (bulk import validation, account checks)
    - Teacher user lookups (profile access)
    - TeacherInvitation teacher FK lookups
    - TeacherInvitation email lookups (invite flow)
    """

    dependencies = [
        ('teachers', '0003_add_teacher_invitation'),
    ]

    operations = [
        # Teacher indexes
        migrations.AddIndex(
            model_name='teacher',
            index=models.Index(
                fields=['email'],
                name='teacher_email_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='teacher',
            index=models.Index(
                fields=['user'],
                name='teacher_user_idx'
            ),
        ),

        # TeacherInvitation indexes
        migrations.AddIndex(
            model_name='teacherinvitation',
            index=models.Index(
                fields=['teacher'],
                name='teacher_inv_teacher_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='teacherinvitation',
            index=models.Index(
                fields=['email'],
                name='teacher_inv_email_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='teacherinvitation',
            index=models.Index(
                fields=['teacher', 'status'],
                name='teacher_inv_teacher_stat_idx'
            ),
        ),
    ]
