from itertools import groupby

from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.db import transaction
from django.contrib import messages

from academics.models import Class
from core.models import AcademicYear
from students.models import Student, Enrollment
from .utils import admin_required, htmx_render


@admin_required
def promotion(request):
    """Show students grouped by class for promotion."""
    current_year = AcademicYear.get_current()
    if not current_year:
        return render(request, 'students/promotion.html', {
            'error': 'No current academic year set. Please configure the academic year first.',
        })

    # Get next academic year
    next_year = AcademicYear.objects.filter(
        start_date__gt=current_year.end_date
    ).order_by('start_date').first()

    # Get all active enrollments for the current year
    enrollments = Enrollment.objects.filter(
        academic_year=current_year,
        status=Enrollment.Status.ACTIVE,
        student__status=Student.Status.ACTIVE
    ).select_related(
        'student', 'class_assigned', 'class_assigned__programme'
    ).order_by(
        'class_assigned__programme__name',
        'class_assigned__level_number',
        'class_assigned__name',
        'student__last_name',
        'student__first_name'
    )

    # Group students by class
    class_students = []
    for key, group in groupby(enrollments, key=lambda e: e.class_assigned):
        students_in_class = [e.student for e in group]
        is_final_year = (
            key.level_type == Class.LevelType.SHS and key.level_number == 3
        )
        class_students.append({
            'class': key,
            'students': students_in_class,
            'count': len(students_in_class),
            'is_final_year': is_final_year,
        })

    # Get all classes for the target dropdown
    all_classes = Class.objects.filter(is_active=True).order_by(
        'programme__name', 'level_number', 'name'
    )

    return htmx_render(
        request,
        'students/promotion.html',
        'students/partials/promotion_content.html',
        {
            'current_year': current_year,
            'next_year': next_year,
            'class_students': class_students,
            'all_classes': all_classes,
        }
    )


@admin_required
def promotion_process(request):
    """Process student promotions."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    current_year = AcademicYear.get_current()
    next_year_id = request.POST.get('next_year')

    if not next_year_id:
        messages.error(request, 'Please select a target academic year.')
        return redirect('students:promotion')

    try:
        next_year = AcademicYear.objects.get(pk=next_year_id)
    except AcademicYear.DoesNotExist:
        messages.error(request, 'Invalid academic year selected.')
        return redirect('students:promotion')

    # Parse POST data to collect all actions
    student_actions = {}  # {student_id: {'action': str, 'target_class_id': str}}
    for key, value in request.POST.items():
        if key.startswith('action_'):
            student_id = key.replace('action_', '')
            if value != 'skip':
                student_actions[student_id] = {
                    'action': value,
                    'target_class_id': request.POST.get(f'target_class_{student_id}')
                }

    if not student_actions:
        messages.info(request, 'No students selected for promotion.')
        return redirect('students:promotion')

    # Bulk fetch all students
    student_ids = list(student_actions.keys())
    students_dict = {
        str(s.pk): s for s in Student.objects.filter(pk__in=student_ids)
    }

    # Bulk fetch all active enrollments for these students in current year
    enrollments_dict = {
        e.student_id: e for e in Enrollment.objects.filter(
            student_id__in=student_ids,
            academic_year=current_year,
            status=Enrollment.Status.ACTIVE
        ).select_related('class_assigned')
    }

    # Collect all target class IDs and bulk fetch
    target_class_ids = [
        data['target_class_id'] for data in student_actions.values()
        if data['target_class_id']
    ]
    classes_dict = {
        str(c.pk): c for c in Class.objects.filter(pk__in=target_class_ids)
    }

    # Process and collect bulk operations
    promoted_count = 0
    repeated_count = 0
    graduated_count = 0
    errors = []

    enrollments_to_update = []
    enrollments_to_create = []
    students_to_update = []

    for student_id, data in student_actions.items():
        action = data['action']
        target_class_id = data['target_class_id']

        student = students_dict.get(student_id)
        if not student:
            errors.append(f'Student ID {student_id}: Not found')
            continue

        current_enrollment = enrollments_dict.get(student.pk)
        if not current_enrollment:
            continue

        if action == 'promote':
            if not target_class_id:
                errors.append(f'{student.full_name}: No target class selected')
                continue

            target_class = classes_dict.get(target_class_id)
            if not target_class:
                errors.append(f'{student.full_name}: Invalid target class')
                continue

            # Mark current enrollment as promoted
            current_enrollment.status = Enrollment.Status.PROMOTED
            enrollments_to_update.append(current_enrollment)

            # Queue new enrollment
            enrollments_to_create.append(Enrollment(
                student=student,
                academic_year=next_year,
                class_assigned=target_class,
                status=Enrollment.Status.ACTIVE,
                promoted_from=current_enrollment,
            ))

            # Update student's current class
            student.current_class = target_class
            students_to_update.append(student)

            promoted_count += 1

        elif action == 'repeat':
            # Mark current enrollment as repeated
            current_enrollment.status = Enrollment.Status.REPEATED
            enrollments_to_update.append(current_enrollment)

            # Queue new enrollment in same class
            enrollments_to_create.append(Enrollment(
                student=student,
                academic_year=next_year,
                class_assigned=current_enrollment.class_assigned,
                status=Enrollment.Status.ACTIVE,
                promoted_from=current_enrollment,
                remarks='Repeated year',
            ))

            repeated_count += 1

        elif action == 'graduate':
            # Mark current enrollment as graduated
            current_enrollment.status = Enrollment.Status.GRADUATED
            enrollments_to_update.append(current_enrollment)

            # Update student status to graduated and clear current class
            student.status = Student.Status.GRADUATED
            student.current_class = None
            students_to_update.append(student)

            graduated_count += 1

    # Execute bulk operations atomically
    with transaction.atomic():
        if enrollments_to_update:
            Enrollment.objects.bulk_update(enrollments_to_update, ['status'])

        if enrollments_to_create:
            Enrollment.objects.bulk_create(enrollments_to_create)

        if students_to_update:
            Student.objects.bulk_update(students_to_update, ['current_class', 'status'])

    # Flash messages
    if promoted_count:
        messages.success(request, f'{promoted_count} student(s) promoted successfully.')
    if repeated_count:
        messages.info(request, f'{repeated_count} student(s) set to repeat.')
    if graduated_count:
        messages.success(request, f'{graduated_count} student(s) graduated successfully.')
    if errors:
        messages.warning(request, f'{len(errors)} error(s) occurred during promotion.')

    return redirect('students:promotion')
