from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add missing database indexes for improved query performance.

    These indexes optimize:
    - StudentGuardian primary guardian lookups
    - Guardian email and user lookups
    - GuardianInvitation pending invitation checks
    """

    dependencies = [
        ('students', '0010_guardian_academic_alerts_and_more'),
    ]

    operations = [
        # StudentGuardian indexes
        migrations.AddIndex(
            model_name='studentguardian',
            index=models.Index(
                fields=['student', 'is_primary'],
                name='sg_student_primary_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='studentguardian',
            index=models.Index(
                fields=['guardian'],
                name='sg_guardian_idx'
            ),
        ),

        # Guardian indexes
        migrations.AddIndex(
            model_name='guardian',
            index=models.Index(
                fields=['email'],
                name='guardian_email_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='guardian',
            index=models.Index(
                fields=['user'],
                name='guardian_user_idx'
            ),
        ),

        # GuardianInvitation indexes
        migrations.AddIndex(
            model_name='guardianinvitation',
            index=models.Index(
                fields=['guardian'],
                name='guardian_inv_guardian_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='guardianinvitation',
            index=models.Index(
                fields=['guardian', 'status'],
                name='guardian_inv_gdn_status_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='guardianinvitation',
            index=models.Index(
                fields=['email'],
                name='guardian_inv_email_idx'
            ),
        ),
    ]
