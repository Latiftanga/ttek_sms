from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse
from django.http import HttpResponse
from django.db.models import Q
from django.contrib import messages
from django.core.paginator import Paginator

from teachers.models import Teacher, TeacherInvitation
from teachers.forms import TeacherForm
from academics.models import Class, ClassSubject, TimetableEntry
from students.models import Student
from .utils import admin_required, htmx_render
from .analytics import calculate_school_averages


@admin_required
def index(request):
    """Teacher list page with search and filter."""
    teachers = Teacher.objects.select_related('user')

    # Search
    search = request.GET.get('search', '').strip()
    if search:
        teachers = teachers.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(staff_id__icontains=search) |
            Q(subject_specialization__icontains=search)
        )

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        teachers = teachers.filter(status=status_filter)

    # Pagination
    per_page = request.GET.get('per_page', '25')
    try:
        per_page = int(per_page)
        if per_page not in [25, 50, 100]:
            per_page = 25
    except ValueError:
        per_page = 25

    paginator = Paginator(teachers.order_by('first_name', 'last_name'), per_page)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'teachers': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'per_page': per_page,
        'status_choices': Teacher.Status.choices,
        'search': search,
        'status_filter': status_filter,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Teachers'},
        ],
    }

    return htmx_render(
        request,
        'teachers/index.html',
        'teachers/partials/index_content.html',
        context
    )


@admin_required
def teacher_create(request):
    """Create a new teacher."""
    breadcrumbs = [
        {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
        {'label': 'Teachers', 'url': '/teachers/'},
        {'label': 'Add Teacher'},
    ]

    if request.method == 'GET':
        form = TeacherForm()
        return htmx_render(
            request,
            'teachers/teacher_form.html',
            'teachers/partials/teacher_form_content.html',
            {'form': form, 'breadcrumbs': breadcrumbs, 'back_url': '/teachers/'}
        )

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = TeacherForm(request.POST, request.FILES)
    if form.is_valid():
        teacher = form.save()
        messages.success(request, f"Teacher {teacher} created successfully.")
        return redirect('teachers:teacher_detail', pk=teacher.pk)

    return htmx_render(
        request,
        'teachers/teacher_form.html',
        'teachers/partials/teacher_form_content.html',
        {'form': form, 'breadcrumbs': breadcrumbs, 'back_url': '/teachers/'}
    )


@admin_required
def teacher_edit(request, pk):
    """Edit an existing teacher."""
    teacher = get_object_or_404(Teacher, pk=pk)

    breadcrumbs = [
        {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
        {'label': 'Teachers', 'url': '/teachers/'},
        {'label': teacher.full_name, 'url': f'/teachers/{pk}/'},
        {'label': 'Edit'},
    ]
    back_url = f'/teachers/{pk}/'

    if request.method == 'GET':
        form = TeacherForm(instance=teacher)
        return htmx_render(
            request,
            'teachers/teacher_form.html',
            'teachers/partials/teacher_form_content.html',
            {'form': form, 'teacher': teacher, 'breadcrumbs': breadcrumbs, 'back_url': back_url}
        )

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = TeacherForm(request.POST, request.FILES, instance=teacher)
    if form.is_valid():
        form.save()
        messages.success(request, "Teacher details updated.")
        return redirect('teachers:teacher_detail', pk=teacher.pk)

    return htmx_render(
        request,
        'teachers/teacher_form.html',
        'teachers/partials/teacher_form_content.html',
        {'form': form, 'teacher': teacher, 'breadcrumbs': breadcrumbs, 'back_url': back_url}
    )


@admin_required
def teacher_detail(request, pk):
    """View teacher details with classes, subjects, and workload."""
    teacher = get_object_or_404(
        Teacher.objects.select_related('user'),
        pk=pk
    )

    # Classes where this teacher is the class teacher (form tutor)
    homeroom_classes = Class.objects.filter(
        class_teacher=teacher,
        is_active=True
    ).order_by('name')

    # Subject assignments - classes and subjects this teacher teaches
    subject_assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name', 'subject__name'
    )

    # Calculate workload stats
    classes_taught = subject_assignments.values('class_assigned').distinct().count()
    subjects_taught = subject_assignments.values('subject').distinct().count()

    # Total students taught (across all classes)
    class_ids = subject_assignments.values_list('class_assigned_id', flat=True).distinct()
    total_students = Student.objects.filter(
        current_class_id__in=class_ids,
        status='active'
    ).count()

    # Periods per week from timetable
    periods_per_week = TimetableEntry.objects.filter(
        class_subject__teacher=teacher
    ).count()

    # Students in homeroom classes
    homeroom_students = Student.objects.filter(
        current_class__in=homeroom_classes,
        status='active'
    ).count()

    workload = {
        'classes_taught': classes_taught,
        'subjects_taught': subjects_taught,
        'total_students': total_students,
        'periods_per_week': periods_per_week,
        'homeroom_classes': homeroom_classes.count(),
        'homeroom_students': homeroom_students,
    }

    # School averages for comparison
    school_averages = calculate_school_averages()

    # Calculate comparison percentages
    def calc_comparison(value, avg):
        if avg == 0:
            return 100 if value > 0 else 0
        return round((value / avg) * 100)

    comparisons = {
        'classes': calc_comparison(classes_taught, school_averages['avg_classes']),
        'subjects': calc_comparison(subjects_taught, school_averages['avg_subjects']),
        'periods': calc_comparison(periods_per_week, school_averages['avg_periods']),
        'students': calc_comparison(total_students, school_averages['avg_students']),
    }

    # Get pending invitation if teacher has no account
    pending_invitation = None
    if not teacher.user:
        pending_invitation = TeacherInvitation.objects.filter(
            teacher=teacher,
            status=TeacherInvitation.Status.PENDING
        ).first()

    return htmx_render(
        request,
        'teachers/teacher_detail.html',
        'teachers/partials/teacher_detail_content.html',
        {
            'teacher': teacher,
            'homeroom_classes': homeroom_classes,
            'subject_assignments': subject_assignments,
            'workload': workload,
            'school_averages': school_averages,
            'comparisons': comparisons,
            'pending_invitation': pending_invitation,
            # Navigation
            'breadcrumbs': [
                {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
                {'label': 'Teachers', 'url': '/teachers/'},
                {'label': teacher.full_name},
            ],
            'back_url': '/teachers/',
        }
    )


@admin_required
def teacher_detail_pdf(request, pk):
    """Download PDF profile for a teacher."""
    import logging
    from io import BytesIO
    from django.template.loader import render_to_string
    from django.conf import settings as django_settings
    from django.db import connection

    logger = logging.getLogger(__name__)

    teacher = get_object_or_404(
        Teacher.objects.select_related('user'),
        pk=pk
    )

    # Classes where this teacher is the class teacher (form tutor)
    homeroom_classes = Class.objects.filter(
        class_teacher=teacher,
        is_active=True
    ).order_by('name')

    # Subject assignments - classes and subjects this teacher teaches
    subject_assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name', 'subject__name'
    )

    # Calculate workload stats
    classes_taught = subject_assignments.values('class_assigned').distinct().count()
    subjects_taught = subject_assignments.values('subject').distinct().count()

    # Total students taught (across all classes)
    class_ids = subject_assignments.values_list('class_assigned_id', flat=True).distinct()
    total_students = Student.objects.filter(
        current_class_id__in=class_ids,
        status='active'
    ).count()

    workload = {
        'classes_taught': classes_taught,
        'subjects_taught': subjects_taught,
        'total_students': total_students,
        'homeroom_classes': homeroom_classes.count(),
    }

    # Get school context with logo
    from gradebook.utils import get_school_context
    school_ctx = get_school_context(include_logo_base64=True)

    # Encode teacher photo if exists
    photo_base64 = None
    if teacher.photo:
        try:
            import base64
            import os
            photo_path = os.path.join(
                django_settings.MEDIA_ROOT,
                'schools',
                connection.schema_name,
                teacher.photo.name.split('/')[-1] if '/' in teacher.photo.name else teacher.photo.name
            )
            # Try direct path first
            if not os.path.exists(photo_path):
                photo_path = teacher.photo.path

            if os.path.exists(photo_path):
                with open(photo_path, 'rb') as f:
                    photo_data = f.read()
                    ext = os.path.splitext(photo_path)[1].lower()
                    mime_types = {
                        '.jpg': 'image/jpeg',
                        '.jpeg': 'image/jpeg',
                        '.png': 'image/png',
                        '.gif': 'image/gif',
                    }
                    mime = mime_types.get(ext, 'image/jpeg')
                    photo_base64 = f"data:{mime};base64,{base64.b64encode(photo_data).decode()}"
        except Exception as e:
            logger.debug(f"Could not encode teacher photo: {e}")

    # Create verification record and generate QR code
    from core.models import DocumentVerification
    from core.utils import generate_verification_qr

    verification = DocumentVerification.create_for_document(
        document_type=DocumentVerification.DocumentType.STAFF_PROFILE,
        teacher=teacher,
        title=f"Staff Record - {teacher.full_name}",
        user=request.user,
    )

    # Generate QR code for verification
    qr_code_base64 = generate_verification_qr(verification.verification_code, request=request)

    context = {
        'teacher': teacher,
        'homeroom_classes': homeroom_classes,
        'subject_assignments': subject_assignments,
        'workload': workload,
        'school': school_ctx['school'],
        'school_settings': school_ctx['school_settings'],
        'logo_base64': school_ctx.get('logo_base64'),
        'photo_base64': photo_base64,
        'verification': verification,
        'qr_code_base64': qr_code_base64,
    }

    # Generate PDF using WeasyPrint
    try:
        from weasyprint import HTML

        html_string = render_to_string('teachers/teacher_detail_pdf.html', context)
        html = HTML(string=html_string, base_url=str(django_settings.BASE_DIR))
        pdf_buffer = BytesIO()
        html.write_pdf(pdf_buffer)
        pdf_buffer.seek(0)

        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="staff_record_{teacher.staff_id}.pdf"'
        return response

    except ImportError:
        logger.error("WeasyPrint not installed")
        messages.error(request, 'PDF generation is not available. WeasyPrint is not installed.')
        return redirect('teachers:teacher_detail', pk=pk)
    except Exception as e:
        import traceback
        logger.error(f"Failed to generate teacher PDF: {str(e)}\n{traceback.format_exc()}")
        messages.error(request, f'Failed to generate PDF: {str(e)}')
        return redirect('teachers:teacher_detail', pk=pk)


@admin_required
def teacher_delete(request, pk):
    """Delete a teacher."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)
    teacher_name = teacher.full_name
    teacher.delete()

    messages.success(request, f'Teacher "{teacher_name}" has been deleted.')

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Redirect'] = reverse('teachers:index')
        return response
    return redirect('teachers:index')


def get_teacher_assignments_context(teacher):
    """Get context for teacher assignments (for OOB swaps)."""
    # Subject assignments
    subject_assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name', 'subject__name'
    )

    # Calculate workload stats
    classes_taught = subject_assignments.values('class_assigned').distinct().count()
    subjects_taught = subject_assignments.values('subject').distinct().count()

    class_ids = subject_assignments.values_list('class_assigned_id', flat=True).distinct()
    total_students = Student.objects.filter(
        current_class_id__in=class_ids,
        status='active'
    ).count()

    periods_per_week = TimetableEntry.objects.filter(
        class_subject__teacher=teacher
    ).count()

    homeroom_classes = Class.objects.filter(
        class_teacher=teacher,
        is_active=True
    )

    workload = {
        'classes_taught': classes_taught,
        'subjects_taught': subjects_taught,
        'total_students': total_students,
        'periods_per_week': periods_per_week,
        'homeroom_classes': homeroom_classes.count(),
    }

    # School averages for comparison
    school_averages = calculate_school_averages()

    # Calculate comparison percentages
    def calc_comparison(value, avg):
        if avg == 0:
            return 100 if value > 0 else 0
        return round((value / avg) * 100)

    comparisons = {
        'classes': calc_comparison(classes_taught, school_averages['avg_classes']),
        'subjects': calc_comparison(subjects_taught, school_averages['avg_subjects']),
        'periods': calc_comparison(periods_per_week, school_averages['avg_periods']),
        'students': calc_comparison(total_students, school_averages['avg_students']),
    }

    return {
        'teacher': teacher,
        'subject_assignments': subject_assignments,
        'workload': workload,
        'school_averages': school_averages,
        'comparisons': comparisons,
    }


@admin_required
def assign_lesson(request, pk):
    """Assign a lesson (class + subject) to a teacher."""
    import json
    from django.shortcuts import render
    from academics.models import Subject

    teacher = get_object_or_404(Teacher, pk=pk)

    # Get all active classes and subjects
    classes = Class.objects.filter(is_active=True).order_by('level_number', 'name')
    subjects = Subject.objects.filter(is_active=True).order_by('name')

    # Get existing assignments for this teacher
    existing_assignments = list(
        ClassSubject.objects.filter(teacher=teacher).values_list('class_assigned_id', 'subject_id')
    )
    # Convert to JSON format for Alpine.js: ["class_id-subject_id", ...]
    existing_assignments_json = json.dumps([f"{c}-{s}" for c, s in existing_assignments])

    if request.method == 'GET':
        return htmx_render(
            request,
            'teachers/partials/modal_assign_lesson.html',
            'teachers/partials/modal_assign_lesson.html',
            {
                'teacher': teacher,
                'classes': classes,
                'subjects': subjects,
                'existing_assignments_json': existing_assignments_json,
            }
        )

    if request.method == 'POST':
        class_id = request.POST.get('class_id')
        subject_id = request.POST.get('subject_id')

        if not class_id or not subject_id:
            messages.error(request, "Please select both a class and a subject.")
            return HttpResponse(status=400)

        class_obj = get_object_or_404(Class, pk=class_id)
        subject = get_object_or_404(Subject, pk=subject_id)

        # Check if already assigned to this teacher
        existing = ClassSubject.objects.filter(
            class_assigned=class_obj,
            subject=subject,
            teacher=teacher
        ).exists()

        if existing:
            # Return modal with warning
            context = get_teacher_assignments_context(teacher)
            context['message'] = f"{teacher.full_name} is already assigned to {subject.name} in {class_obj.name}"
            context['is_warning'] = True
            return render(request, 'teachers/partials/modal_assign_lesson_success.html', context)

        # Check if this class-subject combination already exists
        class_subject, created = ClassSubject.objects.get_or_create(
            class_assigned=class_obj,
            subject=subject,
            defaults={'teacher': teacher}
        )

        message = ""
        if not created:
            if class_subject.teacher == teacher:
                message = f"Already assigned: {subject.name} in {class_obj.name}"
            else:
                # Update the teacher for this assignment
                old_teacher = class_subject.teacher
                class_subject.teacher = teacher
                class_subject.save(update_fields=['teacher'])
                if old_teacher:
                    message = f"Reassigned {subject.name} in {class_obj.name} from {old_teacher.full_name} to {teacher.full_name}"
                else:
                    message = f"Assigned {subject.name} in {class_obj.name} to {teacher.full_name}"
        else:
            message = f"Assigned {subject.name} in {class_obj.name} to {teacher.full_name}"

        # Return success template with OOB swaps
        context = get_teacher_assignments_context(teacher)
        context['message'] = message
        return render(request, 'teachers/partials/modal_assign_lesson_success.html', context)

    return HttpResponse(status=405)


@admin_required
def unassign_lesson(request, pk, assignment_pk):
    """Remove a lesson assignment from a teacher."""
    from django.shortcuts import render

    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)
    assignment = get_object_or_404(ClassSubject, pk=assignment_pk, teacher=teacher)

    # Remove the teacher from this assignment (don't delete the ClassSubject)
    subject_name = assignment.subject.name
    class_name = assignment.class_assigned.name
    assignment.teacher = None
    assignment.save(update_fields=['teacher'])

    message = f"Removed {subject_name} in {class_name} from {teacher.full_name}"

    # Return success template with OOB swaps
    context = get_teacher_assignments_context(teacher)
    context['message'] = message
    context['is_removal'] = True
    return render(request, 'teachers/partials/modal_assign_lesson_success.html', context)
