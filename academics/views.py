from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db import models
from django.contrib import messages

from .models import Programme, Class, Subject, ClassSubject, AttendanceSession, AttendanceRecord
from .forms import ProgrammeForm, ClassForm, SubjectForm, StudentEnrollmentForm, ClassSubjectForm
from students.models import Student


def is_school_admin(user):
    """Check if user is a school admin or superuser."""
    return user.is_superuser or getattr(user, 'is_school_admin', False)


def admin_required(view_func):
    """Decorator to require school admin or superuser access."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not is_school_admin(request.user):
            messages.error(request, "You don't have permission to access this page.")
            return redirect('core:index')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def htmx_render(request, full_template, partial_template, context=None):
    """Render full template for regular requests, partial for HTMX requests."""
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)




def get_academics_context():
    """Get common context for academics page."""
    from django.db.models import Count, Q

    # Get classes with student counts, grouped by level
    classes = Class.objects.select_related('programme', 'class_teacher').annotate(
        student_count=Count('students', filter=models.Q(students__status='active'))
    ).order_by('level_number', 'section')

    # Group classes by level type with stats
    classes_by_level = {
        'kg': {'classes': [], 'student_count': 0},
        'primary': {'classes': [], 'student_count': 0},
        'jhs': {'classes': [], 'student_count': 0},
        'shs': {'classes': [], 'student_count': 0},
    }
    for cls in classes:
        if cls.level_type in classes_by_level:
            classes_by_level[cls.level_type]['classes'].append(cls)
            classes_by_level[cls.level_type]['student_count'] += cls.student_count

    # Programmes with stats
    programmes = Programme.objects.annotate(
        class_count=Count('classes', filter=Q(classes__is_active=True)),
        student_count=Count(
            'classes__students',
            filter=Q(classes__is_active=True, classes__students__status='active')
        )
    ).order_by('name')

    # Subjects with stats
    subjects = Subject.objects.prefetch_related('programmes').annotate(
        class_count=Count(
            'class_allocations',
            filter=Q(class_allocations__class_assigned__is_active=True)
        ),
        student_count=Count(
            'class_allocations__class_assigned__students',
            filter=Q(
                class_allocations__class_assigned__is_active=True,
                class_allocations__class_assigned__students__status='active'
            )
        )
    ).order_by('-is_core', 'name')

    total_students = Student.objects.filter(status='active').count()

    return {
        'programmes': programmes,
        'classes': classes,
        'classes_by_level': classes_by_level,
        'subjects': subjects,
        'stats': {
            'total_classes': classes.count(),
            'total_subjects': subjects.count(),
            'total_programmes': programmes.count(),
            'total_students': total_students,
        },
        'programme_form': ProgrammeForm(),
        'class_form': ClassForm(),
        'subject_form': SubjectForm(),
    }


@admin_required
def index(request):
    """Academics dashboard page - Admin only."""
    context = get_academics_context()

    return htmx_render(
        request,
        'academics/index.html',
        'academics/partials/index_content.html',
        context
    )


# ============ PROGRAMME VIEWS ============

def get_programmes_list_context():
    """Get context for programmes list with stats."""
    from django.db.models import Count, Q

    programmes = Programme.objects.annotate(
        class_count=Count('classes', filter=Q(classes__is_active=True)),
        student_count=Count(
            'classes__students',
            filter=Q(classes__is_active=True, classes__students__status='active')
        )
    ).order_by('name')

    return {'programmes': programmes}


@admin_required
def programme_create(request):
    """Create a new programme."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ProgrammeForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/programmes_list.html', get_programmes_list_context())
            response['HX-Trigger'] = 'closeModal'
            return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_programme_form.html', {
            'form': form,
            'is_create': True,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@admin_required
def programme_edit(request, pk):
    """Edit a programme."""
    programme = get_object_or_404(Programme, pk=pk)

    if request.method == 'GET':
        form = ProgrammeForm(instance=programme)
        return render(request, 'academics/partials/modal_programme_form.html', {
            'form': form,
            'programme': programme,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ProgrammeForm(request.POST, instance=programme)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/programmes_list.html', get_programmes_list_context())
            response['HX-Trigger'] = 'closeModal'
            return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_programme_form.html', {
            'form': form,
            'programme': programme,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@login_required
def programme_delete(request, pk):
    """Delete a programme."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    programme = get_object_or_404(Programme, pk=pk)
    programme.delete()

    if request.htmx:
        return render(request, 'academics/partials/programmes_list.html', get_programmes_list_context())
    return redirect('academics:index')


# ============ CLASS VIEWS ============

def get_classes_list_context():
    """Get context for classes list."""
    from django.db.models import Count
    classes = Class.objects.select_related('programme', 'class_teacher').annotate(
        student_count=Count('students', filter=models.Q(students__status='active'))
    ).order_by('level_number', 'section')
    return {'classes': classes}


@login_required
def class_create(request):
    """Create a new class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ClassForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/classes_list.html', get_classes_list_context())
            response['HX-Trigger'] = 'closeModal'
            return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_class_form.html', {
            'form': form,
            'is_create': True,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@login_required
def class_edit(request, pk):
    """Edit a class."""
    cls = get_object_or_404(Class, pk=pk)

    # Check if editing from class detail page
    current_url = request.headers.get('HX-Current-URL', '')
    is_detail_page = f'/academics/classes/{pk}/' in current_url

    if request.method == 'GET':
        form = ClassForm(instance=cls)
        return render(request, 'academics/partials/modal_class_form.html', {
            'form': form,
            'class': cls,
            'is_detail_page': is_detail_page,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ClassForm(request.POST, instance=cls)
    if form.is_valid():
        form.save()
        if request.htmx:
            if is_detail_page:
                # On detail page, refresh to show updated data
                response = HttpResponse(status=204)
                response['HX-Refresh'] = 'true'
                return response
            else:
                # On index page, update the classes list
                response = render(request, 'academics/partials/classes_list.html', get_classes_list_context())
                response['HX-Trigger'] = 'closeModal'
                return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_class_form.html', {
            'form': form,
            'class': cls,
            'is_detail_page': is_detail_page,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@login_required
def class_delete(request, pk):
    """Delete a class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    cls = get_object_or_404(Class, pk=pk)
    cls.delete()

    if request.htmx:
        return render(request, 'academics/partials/classes_list.html', get_classes_list_context())
    return redirect('academics:index')


# ============ SUBJECT VIEWS ============

def get_subjects_list_context():
    """Get context for subjects list with stats."""
    from django.db.models import Count, Q

    subjects = Subject.objects.prefetch_related('programmes').annotate(
        class_count=Count(
            'class_allocations',
            filter=Q(class_allocations__class_assigned__is_active=True)
        ),
        student_count=Count(
            'class_allocations__class_assigned__students',
            filter=Q(
                class_allocations__class_assigned__is_active=True,
                class_allocations__class_assigned__students__status='active'
            )
        )
    ).order_by('-is_core', 'name')

    return {'subjects': subjects}


@login_required
def subject_create(request):
    """Create a new subject."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    form = SubjectForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/subjects_list.html', get_subjects_list_context())
            response['HX-Trigger'] = 'closeModal'
            return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_subject_form.html', {
            'form': form,
            'is_create': True,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@login_required
def subject_edit(request, pk):
    """Edit a subject."""
    subject = get_object_or_404(Subject, pk=pk)

    if request.method == 'GET':
        form = SubjectForm(instance=subject)
        return render(request, 'academics/partials/modal_subject_form.html', {
            'form': form,
            'subject': subject,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = SubjectForm(request.POST, instance=subject)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/subjects_list.html', get_subjects_list_context())
            response['HX-Trigger'] = 'closeModal'
            return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_subject_form.html', {
            'form': form,
            'subject': subject,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@login_required
def subject_delete(request, pk):
    """Delete a subject."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    subject = get_object_or_404(Subject, pk=pk)
    subject.delete()

    if request.htmx:
        return render(request, 'academics/partials/subjects_list.html', get_subjects_list_context())
    return redirect('academics:index')



def get_register_tab_context(class_obj):
    """Context for the Students/Register tab."""
    students = Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).order_by('first_name')

    # Gender breakdown
    male_count = students.filter(gender='M').count()
    female_count = students.filter(gender='F').count()

    return {
        'class': class_obj,
        'students': students,
        'gender_stats': {
            'male': male_count,
            'female': female_count,
        }
    }

def get_teachers_tab_context(class_obj):
    """Context for the Teachers/Subjects tab."""
    subject_allocations = ClassSubject.objects.filter(
        class_assigned=class_obj
    ).select_related('subject', 'teacher').order_by('subject__name')
    return {
        'class': class_obj,
        'subject_allocations': subject_allocations
    }

def get_attendance_tab_context(class_obj):
    """Context for the Attendance tab with real data."""
    from django.db.models import Count, Q

    sessions = AttendanceSession.objects.filter(
        class_assigned=class_obj
    ).annotate(
        present_count=Count('records', filter=Q(records__status__in=['P', 'L'])),
        absent_count=Count('records', filter=Q(records__status='A')),
        total_count=Count('records')
    ).order_by('-date')

    # Calculate overall attendance percentage
    total_records = AttendanceRecord.objects.filter(
        session__class_assigned=class_obj
    ).count()
    present_count = AttendanceRecord.objects.filter(
        session__class_assigned=class_obj,
        status__in=['P', 'L']  # Present or Late counts as present
    ).count()

    if total_records > 0:
        attendance_percentage = int((present_count / total_records) * 100)
    else:
        attendance_percentage = "--"

    return {
        'class': class_obj,
        'attendance_sessions': sessions,
        'attendance_percentage': attendance_percentage,
    }


def get_promotion_history_context(class_obj):
    """Context for showing recent enrollment/promotion activity for this class."""
    from students.models import Enrollment
    from core.models import AcademicYear

    current_year = AcademicYear.get_current()

    # Get recent enrollments for this class (incoming students)
    incoming_enrollments = Enrollment.objects.filter(
        class_assigned=class_obj
    ).select_related('student', 'academic_year', 'promoted_from').order_by(
        '-created_at'
    )[:5]

    # Get promotions/graduations out of this class
    outgoing_enrollments = Enrollment.objects.filter(
        promoted_from__class_assigned=class_obj
    ).select_related('student', 'academic_year', 'class_assigned').order_by(
        '-created_at'
    )[:5]

    # Summary stats
    if current_year:
        active_in_current_year = Enrollment.objects.filter(
            class_assigned=class_obj,
            academic_year=current_year,
            status=Enrollment.Status.ACTIVE
        ).count()

        promoted_count = Enrollment.objects.filter(
            promoted_from__class_assigned=class_obj,
            promoted_from__academic_year=current_year
        ).count()

        graduated_count = Enrollment.objects.filter(
            class_assigned=class_obj,
            academic_year=current_year,
            status=Enrollment.Status.GRADUATED
        ).count()
    else:
        active_in_current_year = 0
        promoted_count = 0
        graduated_count = 0

    return {
        'incoming_enrollments': incoming_enrollments,
        'outgoing_enrollments': outgoing_enrollments,
        'promotion_stats': {
            'active': active_in_current_year,
            'promoted': promoted_count,
            'graduated': graduated_count,
        },
        'current_year': current_year,
    }

# --- Main Detail View ---

@login_required
def class_detail(request, pk):
    """Detailed view of a specific class."""
    class_obj = get_object_or_404(Class, pk=pk)

    # Base context
    context = {
        'class': class_obj,
    }

    # Combine all tab contexts for the initial page load
    context.update(get_register_tab_context(class_obj))
    context.update(get_teachers_tab_context(class_obj))
    context.update(get_attendance_tab_context(class_obj))
    context.update(get_promotion_history_context(class_obj))

    return htmx_render(
        request,
        'academics/class_detail.html',
        'academics/partials/class_detail_content.html',
        context
    )

# --- Action Views (Using Helpers) ---
@login_required
def class_subject_create(request, pk):
    class_obj = get_object_or_404(Class, pk=pk)

    if request.method == 'POST':
        form = ClassSubjectForm(request.POST, class_instance=class_obj)
        if form.is_valid():
            allocation = form.save(commit=False)
            allocation.class_assigned = class_obj
            allocation.save()

            if request.htmx:
                response = HttpResponse(status=204)
                response['HX-Refresh'] = 'true'
                return response

            return redirect('academics:class_detail', pk=pk)
    else:
        form = ClassSubjectForm(class_instance=class_obj)

    return render(request, 'academics/partials/modal_subject_allocation.html', {
        'form': form, 'class': class_obj
    })


@login_required
def class_subject_delete(request, class_pk, pk):
    allocation = get_object_or_404(ClassSubject, pk=pk, class_assigned_id=class_pk)
    allocation.delete()

    if request.htmx:
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    return redirect('academics:class_detail', pk=class_pk)


@login_required
def class_student_enroll(request, pk):
    """Enroll existing students into a class."""
    class_obj = get_object_or_404(Class, pk=pk)

    if request.method == 'POST':
        form = StudentEnrollmentForm(request.POST, class_instance=class_obj)
        if form.is_valid():
            students_to_add = form.cleaned_data['students']
            for student in students_to_add:
                student.current_class = class_obj
                student.save()

            if request.htmx:
                response = HttpResponse(status=204)
                response['HX-Refresh'] = 'true'
                return response

            return redirect('academics:class_detail', pk=pk)
    else:
        form = StudentEnrollmentForm(class_instance=class_obj)

    return render(request, 'academics/partials/modal_student_enroll.html', {
        'form': form, 'class': class_obj
    })


@login_required
def class_student_remove(request, class_pk, student_pk):
    """Remove a student from a class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    student = get_object_or_404(Student, pk=student_pk, current_class_id=class_pk)
    student.current_class = None
    student.save()

    if request.htmx:
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    return redirect('academics:class_detail', pk=class_pk)


# --- 2. Take Attendance Action ---
@login_required
def class_attendance_take(request, pk):
    """
    Opens the attendance sheet for a specific date (defaults to today).
    Handles saving the records.
    """
    class_obj = get_object_or_404(Class, pk=pk)
    target_date = timezone.now().date() # For now, default to today
    
    # Check if session exists
    session, created = AttendanceSession.objects.get_or_create(
        class_assigned=class_obj,
        date=target_date
    )

    if request.method == 'POST':
        # Process the form submission manually for grid data
        # Data format: "status_STUDENTID" : "STATUS_CODE"
        
        students = Student.objects.filter(current_class=class_obj, status='active')
        
        for student in students:
            status_key = f"status_{student.id}"
            new_status = request.POST.get(status_key, AttendanceRecord.Status.PRESENT)
            
            AttendanceRecord.objects.update_or_create(
                session=session,
                student=student,
                defaults={'status': new_status}
            )
            
        # HTMX Success: Refresh page to show updated data
        if request.htmx:
            response = HttpResponse(status=204)
            response['HX-Refresh'] = 'true'
            return response

        return redirect('academics:class_detail', pk=pk)

    # GET Request: Prepare data for the form
    students = Student.objects.filter(current_class=class_obj, status='active').order_by('first_name')
    records = {r.student_id: r.status for r in session.records.all()}
    
    # Combine student + their status
    student_list = []
    for student in students:
        student_list.append({
            'obj': student,
            'status': records.get(student.id, 'P') # Default to Present if new
        })

    return render(request, 'academics/partials/modal_attendance_take.html', {
        'class': class_obj,
        'session': session,
        'student_list': student_list,
        'date': target_date
    })


@login_required
def class_promote(request, pk):
    """Promote students from a specific class (modal-based)."""
    from students.models import Enrollment
    from core.models import AcademicYear

    class_obj = get_object_or_404(Class, pk=pk)
    current_year = AcademicYear.get_current()

    if not current_year:
        return render(request, 'academics/partials/modal_class_promote.html', {
            'class': class_obj,
            'error': 'No current academic year set.',
        })

    # Get next academic year
    next_year = AcademicYear.objects.filter(
        start_date__gt=current_year.end_date
    ).order_by('start_date').first()

    if not next_year:
        return render(request, 'academics/partials/modal_class_promote.html', {
            'class': class_obj,
            'error': 'No next academic year configured. Please create one first.',
        })

    # Determine if this is a final-year class
    is_final_year = (
        class_obj.level_type == Class.LevelType.SHS and class_obj.level_number == 3
    )

    # Get students with active enrollments in this class for current year
    students = Student.objects.filter(
        enrollments__class_assigned=class_obj,
        enrollments__academic_year=current_year,
        enrollments__status=Enrollment.Status.ACTIVE,
        status=Student.Status.ACTIVE
    ).select_related('current_class').order_by('last_name', 'first_name')

    if request.method == 'POST':
        from django.contrib import messages

        promoted_count = 0
        repeated_count = 0
        graduated_count = 0
        errors = []

        for key, value in request.POST.items():
            if key.startswith('action_'):
                student_id = key.replace('action_', '')
                action = value

                if action == 'skip':
                    continue

                try:
                    student = Student.objects.get(pk=student_id)
                    current_enrollment = student.enrollments.filter(
                        academic_year=current_year,
                        class_assigned=class_obj,
                        status=Enrollment.Status.ACTIVE
                    ).first()

                    if not current_enrollment:
                        continue

                    if action == 'promote':
                        target_class_id = request.POST.get(f'target_class_{student_id}')
                        if not target_class_id:
                            errors.append(f'{student.full_name}: No target class selected')
                            continue

                        try:
                            target_class = Class.objects.get(pk=target_class_id)
                        except Class.DoesNotExist:
                            errors.append(f'{student.full_name}: Invalid target class')
                            continue

                        current_enrollment.status = Enrollment.Status.PROMOTED
                        current_enrollment.save()

                        Enrollment.objects.create(
                            student=student,
                            academic_year=next_year,
                            class_assigned=target_class,
                            status=Enrollment.Status.ACTIVE,
                            promoted_from=current_enrollment,
                        )

                        student.current_class = target_class
                        student.save()
                        promoted_count += 1

                    elif action == 'repeat':
                        current_enrollment.status = Enrollment.Status.REPEATED
                        current_enrollment.save()

                        Enrollment.objects.create(
                            student=student,
                            academic_year=next_year,
                            class_assigned=class_obj,
                            status=Enrollment.Status.ACTIVE,
                            promoted_from=current_enrollment,
                            remarks='Repeated year',
                        )
                        repeated_count += 1

                    elif action == 'graduate':
                        current_enrollment.status = Enrollment.Status.GRADUATED
                        current_enrollment.save()

                        student.status = Student.Status.GRADUATED
                        student.current_class = None
                        student.save()
                        graduated_count += 1

                except Student.DoesNotExist:
                    errors.append(f'Student ID {student_id}: Not found')
                except Exception as e:
                    errors.append(f'Error: {str(e)}')

        # HTMX Response: Refresh page to show updated data
        if request.htmx:
            response = HttpResponse(status=204)
            response['HX-Refresh'] = 'true'
            return response

        return redirect('academics:class_detail', pk=pk)

    # GET: Prepare form data
    all_target_classes = Class.objects.filter(is_active=True).order_by(
        'programme__name', 'level_number', 'name'
    )

    return render(request, 'academics/partials/modal_class_promote.html', {
        'class': class_obj,
        'students': students,
        'is_final_year': is_final_year,
        'current_year': current_year,
        'next_year': next_year,
        'all_classes': all_target_classes,
    })


@login_required
def class_attendance_edit(request, pk, session_pk):
    """Edit an existing attendance session."""
    class_obj = get_object_or_404(Class, pk=pk)
    session = get_object_or_404(AttendanceSession, pk=session_pk, class_assigned=class_obj)

    if request.method == 'POST':
        students = Student.objects.filter(current_class=class_obj, status='active')

        for student in students:
            status_key = f"status_{student.id}"
            new_status = request.POST.get(status_key, AttendanceRecord.Status.PRESENT)

            AttendanceRecord.objects.update_or_create(
                session=session,
                student=student,
                defaults={'status': new_status}
            )

        if request.htmx:
            response = HttpResponse(status=204)
            response['HX-Refresh'] = 'true'
            return response

        return redirect('academics:class_detail', pk=pk)

    # GET Request: Load existing records
    students = Student.objects.filter(current_class=class_obj, status='active').order_by('first_name')
    records = {r.student_id: r.status for r in session.records.all()}

    student_list = []
    for student in students:
        student_list.append({
            'obj': student,
            'status': records.get(student.id, 'P')
        })

    return render(request, 'academics/partials/modal_attendance_take.html', {
        'class': class_obj,
        'session': session,
        'student_list': student_list,
        'date': session.date,
        'is_edit': True
    })


@login_required
def class_export(request, pk):
    """Export class register to Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter
    from django.http import HttpResponse as DjangoHttpResponse
    from core.models import SchoolSettings

    class_obj = get_object_or_404(Class, pk=pk)
    students = Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).order_by('last_name', 'first_name')

    school = SchoolSettings.load()

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = f"{class_obj.name} Register"

    # Styles
    header_font = Font(bold=True, size=14)
    subheader_font = Font(bold=True, size=11)
    table_header_font = Font(bold=True, size=10, color="FFFFFF")
    table_header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # School Header
    ws.merge_cells('A1:F1')
    ws['A1'] = school.display_name or request.tenant.name
    ws['A1'].font = header_font
    ws['A1'].alignment = Alignment(horizontal='center')

    # Class Info
    ws.merge_cells('A2:F2')
    ws['A2'] = f"{class_obj.name} - {class_obj.level_display}"
    ws['A2'].font = subheader_font
    ws['A2'].alignment = Alignment(horizontal='center')

    # Date
    ws.merge_cells('A3:F3')
    ws['A3'] = f"Generated: {timezone.now().strftime('%B %d, %Y')}"
    ws['A3'].alignment = Alignment(horizontal='center')

    # Empty row
    ws.append([])

    # Table Headers
    headers = ['#', 'Admission No.', 'Full Name', 'Gender', 'Guardian', 'Phone']
    ws.append(headers)
    header_row = 5

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_num)
        cell.font = table_header_font
        cell.fill = table_header_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = border

    # Student Data
    for idx, student in enumerate(students, 1):
        row_data = [
            idx,
            student.admission_number,
            student.full_name,
            student.get_gender_display(),
            student.guardian_name or '-',
            student.guardian_phone or '-',
        ]
        ws.append(row_data)

        # Apply borders
        for col_num in range(1, len(row_data) + 1):
            cell = ws.cell(row=header_row + idx, column=col_num)
            cell.border = border
            if col_num == 1:
                cell.alignment = Alignment(horizontal='center')

    # Set column widths
    column_widths = [5, 15, 30, 10, 25, 15]
    for i, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # Summary row
    summary_row = header_row + len(students) + 2
    ws.cell(row=summary_row, column=1, value=f"Total Students: {students.count()}")
    ws.cell(row=summary_row, column=1).font = Font(bold=True)

    male_count = students.filter(gender='M').count()
    female_count = students.filter(gender='F').count()
    ws.cell(row=summary_row + 1, column=1, value=f"Male: {male_count} | Female: {female_count}")

    # Create response
    response = DjangoHttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"{class_obj.name.replace(' ', '_')}_Register.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    wb.save(response)
    return response


# ============ ATTENDANCE REPORTS ============

@login_required
def attendance_reports(request):
    """Attendance reports with filters."""
    from django.db.models import Count, Q, F
    from datetime import timedelta
    from teachers.models import Teacher

    user = request.user
    is_admin = user.is_superuser or getattr(user, 'is_school_admin', False)

    # Get filter parameters
    class_filter = request.GET.get('class', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    view_mode = request.GET.get('view', 'summary')  # summary, daily, students

    # Default date range: last 30 days
    today = timezone.now().date()
    if not date_from:
        date_from = (today - timedelta(days=30)).isoformat()
    if not date_to:
        date_to = today.isoformat()

    # Filter classes based on user role
    if is_admin:
        classes = Class.objects.filter(is_active=True).order_by('level_number', 'name')
    elif getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile'):
        teacher = user.teacher_profile
        # Teachers see classes they're class teacher for OR assigned to teach
        homeroom_ids = Class.objects.filter(class_teacher=teacher).values_list('id', flat=True)
        assigned_ids = ClassSubject.objects.filter(teacher=teacher).values_list('class_assigned_id', flat=True)
        all_class_ids = set(homeroom_ids) | set(assigned_ids)
        classes = Class.objects.filter(id__in=all_class_ids, is_active=True).order_by('level_number', 'name')
    else:
        classes = Class.objects.none()

    allowed_class_ids = list(classes.values_list('id', flat=True))

    # Base querysets - filter by allowed classes for teachers
    sessions = AttendanceSession.objects.select_related('class_assigned')
    records = AttendanceRecord.objects.select_related('session', 'student', 'session__class_assigned')

    if not is_admin:
        sessions = sessions.filter(class_assigned_id__in=allowed_class_ids)
        records = records.filter(session__class_assigned_id__in=allowed_class_ids)

    # Apply date filter
    if date_from:
        sessions = sessions.filter(date__gte=date_from)
        records = records.filter(session__date__gte=date_from)
    if date_to:
        sessions = sessions.filter(date__lte=date_to)
        records = records.filter(session__date__lte=date_to)

    # Apply class filter
    if class_filter:
        sessions = sessions.filter(class_assigned_id=class_filter)
        records = records.filter(session__class_assigned_id=class_filter)

    # Calculate summary stats
    total_sessions = sessions.count()
    total_records = records.count()
    present_count = records.filter(status__in=['P', 'L']).count()
    absent_count = records.filter(status='A').count()
    late_count = records.filter(status='L').count()

    attendance_rate = 0
    if total_records > 0:
        attendance_rate = round((present_count / total_records) * 100, 1)

    # Summary by class (only for allowed classes)
    class_summary = []
    for cls in classes:
        cls_records = records.filter(session__class_assigned=cls)
        cls_total = cls_records.count()
        if cls_total > 0:
            cls_present = cls_records.filter(status__in=['P', 'L']).count()
            cls_absent = cls_records.filter(status='A').count()
            cls_rate = round((cls_present / cls_total) * 100, 1)
            class_summary.append({
                'class': cls,
                'total': cls_total,
                'present': cls_present,
                'absent': cls_absent,
                'rate': cls_rate,
            })

    # Daily breakdown (for daily view)
    daily_data = []
    if view_mode == 'daily':
        daily_sessions = sessions.order_by('-date')[:30]
        for session in daily_sessions:
            session_records = session.records.all()
            s_total = session_records.count()
            s_present = session_records.filter(status__in=['P', 'L']).count()
            s_absent = session_records.filter(status='A').count()
            daily_data.append({
                'session': session,
                'total': s_total,
                'present': s_present,
                'absent': s_absent,
                'rate': round((s_present / s_total) * 100, 1) if s_total > 0 else 0,
            })

    # Students with low attendance (for students view)
    low_attendance_students = []
    if view_mode == 'students':
        # Get students with attendance below 80%
        student_stats = {}
        for record in records:
            sid = record.student_id
            if sid not in student_stats:
                student_stats[sid] = {'student': record.student, 'total': 0, 'present': 0}
            student_stats[sid]['total'] += 1
            if record.status in ['P', 'L']:
                student_stats[sid]['present'] += 1

        for sid, stats in student_stats.items():
            if stats['total'] > 0:
                rate = round((stats['present'] / stats['total']) * 100, 1)
                if rate < 80:  # Low attendance threshold
                    low_attendance_students.append({
                        'student': stats['student'],
                        'total': stats['total'],
                        'present': stats['present'],
                        'absent': stats['total'] - stats['present'],
                        'rate': rate,
                    })

        # Sort by attendance rate (lowest first)
        low_attendance_students.sort(key=lambda x: x['rate'])

    context = {
        'classes': classes,
        'class_filter': class_filter,
        'date_from': date_from,
        'date_to': date_to,
        'view_mode': view_mode,
        'stats': {
            'total_sessions': total_sessions,
            'total_records': total_records,
            'present': present_count,
            'absent': absent_count,
            'late': late_count,
            'rate': attendance_rate,
        },
        'class_summary': class_summary,
        'daily_data': daily_data,
        'low_attendance_students': low_attendance_students,
    }

    return htmx_render(
        request,
        'academics/attendance_reports.html',
        'academics/partials/attendance_reports_content.html',
        context
    )


@login_required
def attendance_export(request):
    """Export attendance data to Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter
    from django.http import HttpResponse as DjangoHttpResponse
    from core.models import SchoolSettings
    from datetime import timedelta

    # Get filter parameters
    class_filter = request.GET.get('class', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # Default date range
    today = timezone.now().date()
    if not date_from:
        date_from = (today - timedelta(days=30)).isoformat()
    if not date_to:
        date_to = today.isoformat()

    school = SchoolSettings.load()

    # Get records
    records = AttendanceRecord.objects.select_related(
        'session', 'student', 'session__class_assigned'
    ).filter(
        session__date__gte=date_from,
        session__date__lte=date_to
    ).order_by('session__date', 'session__class_assigned__name', 'student__last_name')

    if class_filter:
        records = records.filter(session__class_assigned_id=class_filter)

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance Report"

    # Styles
    header_font = Font(bold=True, size=14)
    subheader_font = Font(bold=True, size=11)
    table_header_font = Font(bold=True, size=10, color="FFFFFF")
    table_header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    present_fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
    absent_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    late_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # Header
    ws.merge_cells('A1:F1')
    ws['A1'] = school.display_name or request.tenant.name
    ws['A1'].font = header_font
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:F2')
    ws['A2'] = f"Attendance Report: {date_from} to {date_to}"
    ws['A2'].font = subheader_font
    ws['A2'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A3:F3')
    ws['A3'] = f"Generated: {timezone.now().strftime('%B %d, %Y %I:%M %p')}"
    ws['A3'].alignment = Alignment(horizontal='center')

    ws.append([])

    # Table headers
    headers = ['Date', 'Class', 'Student Name', 'Admission No.', 'Status', 'Remarks']
    ws.append(headers)
    header_row = 5

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_num)
        cell.font = table_header_font
        cell.fill = table_header_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = border

    # Data rows
    status_map = {'P': 'Present', 'A': 'Absent', 'L': 'Late', 'E': 'Excused'}
    for idx, record in enumerate(records, 1):
        row_data = [
            record.session.date.strftime('%Y-%m-%d'),
            record.session.class_assigned.name,
            record.student.full_name,
            record.student.admission_number,
            status_map.get(record.status, record.status),
            record.remarks or '',
        ]
        ws.append(row_data)

        row_num = header_row + idx
        for col_num in range(1, len(row_data) + 1):
            cell = ws.cell(row=row_num, column=col_num)
            cell.border = border

        # Color-code status
        status_cell = ws.cell(row=row_num, column=5)
        if record.status == 'P':
            status_cell.fill = present_fill
        elif record.status == 'A':
            status_cell.fill = absent_fill
        elif record.status == 'L':
            status_cell.fill = late_fill

    # Column widths
    column_widths = [12, 15, 30, 15, 12, 25]
    for i, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # Summary
    summary_row = header_row + records.count() + 2
    ws.cell(row=summary_row, column=1, value=f"Total Records: {records.count()}")
    ws.cell(row=summary_row, column=1).font = Font(bold=True)

    present = records.filter(status__in=['P', 'L']).count()
    absent = records.filter(status='A').count()
    rate = round((present / records.count()) * 100, 1) if records.count() > 0 else 0
    ws.cell(row=summary_row + 1, column=1, value=f"Present: {present} | Absent: {absent} | Rate: {rate}%")

    # Response
    response = DjangoHttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"Attendance_Report_{date_from}_to_{date_to}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    wb.save(response)
    return response


# ============ API ENDPOINTS ============

@login_required
def api_class_subjects(request, pk):
    """API endpoint to get subjects for a class.

    For admins: returns all subjects assigned to the class.
    For teachers: returns only subjects they are assigned to teach.
    """
    class_obj = get_object_or_404(Class, pk=pk)
    user = request.user

    # Build base query
    class_subjects = ClassSubject.objects.filter(
        class_assigned=class_obj
    ).select_related('subject', 'teacher')

    # Filter by teacher assignment for non-admins
    if not (user.is_superuser or getattr(user, 'is_school_admin', False)):
        # Check if user has a teacher profile
        if hasattr(user, 'teacher_profile') and user.teacher_profile:
            class_subjects = class_subjects.filter(teacher=user.teacher_profile)
        else:
            class_subjects = class_subjects.none()

    subjects = [
        {
            'id': cs.subject.pk,
            'name': cs.subject.name,
            'is_assigned': cs.teacher_id == getattr(getattr(user, 'teacher_profile', None), 'id', None)
        }
        for cs in class_subjects
    ]

    return JsonResponse({'subjects': subjects})