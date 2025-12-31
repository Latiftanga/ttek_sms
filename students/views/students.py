from django.shortcuts import redirect, get_object_or_404
from django.http import HttpResponse
from django.db.models import Q

from academics.models import Class
from students.models import Student
from students.forms import StudentForm, GuardianForm
from .utils import admin_required, htmx_render, create_enrollment_for_student


@admin_required
def index(request):
    """Student list page with search and filter."""
    students = Student.objects.select_related('current_class', 'guardian').all()

    # Search
    search = request.GET.get('search', '').strip()
    if search:
        students = students.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(other_names__icontains=search) |
            Q(admission_number__icontains=search)
        )

    # Filter by class
    class_filter = request.GET.get('class', '')
    if class_filter:
        students = students.filter(current_class_id=class_filter)

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        students = students.filter(status=status_filter)

    context = {
        'students': students,
        'classes': Class.objects.filter(is_active=True),
        'status_choices': Student.Status.choices,
        'search': search,
        'class_filter': class_filter,
        'status_filter': status_filter,
        'form': StudentForm(),
        'guardian_form': GuardianForm(),
    }

    return htmx_render(
        request,
        'students/index.html',
        'students/partials/index_content.html',
        context
    )


@admin_required
def student_create(request):
    """Create a new student."""
    if request.method == 'GET':
        form = StudentForm()
        return htmx_render(
            request,
            'students/student_form.html',
            'students/partials/student_form_content.html',
            {'form': form}
        )

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = StudentForm(request.POST, request.FILES)
    if form.is_valid():
        student = form.save()
        # Auto-create enrollment for current academic year
        enrollment, created = create_enrollment_for_student(student)
        if created:
            student.current_class = enrollment.class_assigned
            student.save()
        return redirect('students:index')

    return htmx_render(
        request,
        'students/student_form.html',
        'students/partials/student_form_content.html',
        {'form': form}
    )


@admin_required
def student_edit(request, pk):
    """Edit a student."""
    student = get_object_or_404(Student, pk=pk)

    if request.method == 'GET':
        form = StudentForm(instance=student)
        return htmx_render(
            request,
            'students/student_form.html',
            'students/partials/student_form_content.html',
            {'form': form, 'student': student}
        )

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = StudentForm(request.POST, request.FILES, instance=student)
    if form.is_valid():
        student = form.save()
        # Ensure current_class is updated if changed in the form
        enrollment, created = create_enrollment_for_student(student)
        if created:
            student.current_class = enrollment.class_assigned
            student.save()
        return redirect('students:index')

    return htmx_render(
        request,
        'students/student_form.html',
        'students/partials/student_form_content.html',
        {'form': form, 'student': student}
    )


@admin_required
def student_delete(request, pk):
    """Delete a student."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    student = get_object_or_404(Student, pk=pk)
    student.delete()

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('students:index')


@admin_required
def student_detail(request, pk):
    """View student details."""
    student = get_object_or_404(
        Student.objects.select_related('current_class', 'user', 'guardian'),
        pk=pk
    )
    enrollments = student.get_enrollment_history()
    return htmx_render(
        request,
        'students/student_detail.html',
        'students/partials/student_detail_content.html',
        {
            'student': student,
            'enrollments': enrollments,
        }
    )
