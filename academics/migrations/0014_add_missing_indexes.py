from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add missing database indexes for improved query performance.

    These indexes optimize:
    - Student subject enrollment lookups
    - Attendance session filtering by class and date
    - Attendance record lookups by session and student
    - Class lookups by class teacher
    - ClassSubject lookups by teacher
    """

    dependencies = [
        ('academics', '0013_merge_primary_jhs_to_basic'),
    ]

    operations = [
        # StudentSubjectEnrollment indexes
        migrations.AddIndex(
            model_name='studentsubjectenrollment',
            index=models.Index(
                fields=['student', 'is_active'],
                name='sse_student_active_idx'
            ),
        ),

        # AttendanceSession indexes
        migrations.AddIndex(
            model_name='attendancesession',
            index=models.Index(
                fields=['class_assigned', 'date'],
                name='attsess_class_date_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='attendancesession',
            index=models.Index(
                fields=['date'],
                name='attsess_date_idx'
            ),
        ),

        # AttendanceRecord indexes
        migrations.AddIndex(
            model_name='attendancerecord',
            index=models.Index(
                fields=['session', 'student'],
                name='attrec_sess_stud_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='attendancerecord',
            index=models.Index(
                fields=['student', 'status'],
                name='attrec_stud_status_idx'
            ),
        ),

        # Class index for teacher lookup
        migrations.AddIndex(
            model_name='class',
            index=models.Index(
                fields=['class_teacher'],
                name='class_teacher_idx'
            ),
        ),

        # ClassSubject index for teacher lookup
        migrations.AddIndex(
            model_name='classsubject',
            index=models.Index(
                fields=['teacher'],
                name='classsub_teacher_idx'
            ),
        ),
    ]
