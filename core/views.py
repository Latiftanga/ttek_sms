from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from .models import Tenant, Student, Teacher


def school_dashboard(request):
    """Main dashboard for each school"""
    if not request.tenant:
        return HttpResponse(
            "<h1>No School Found</h1><p>This domain is not associated with any school.</p>",
            status=404
        )

    school = request.tenant

    # Get school statistics
    students = Student.objects.active_for_school(school)
    teachers = Teacher.objects.active_for_school(school)

    # Recent students (last 10)
    recent_students = students.order_by('-created_at')[:10]

    context = {
        'school': school,
        'students': students,
        'teachers': teachers,
        'recent_students': recent_students,
        'student_count': students.count(),
        'teacher_count': teachers.count(),
        'page_title': f'{school.name} - Dashboard'
    }

    return render(request, 'core/dashboard.html', context)


def school_about(request):
    """About page for each school"""
    if not request.tenant:
        raise Http404("School not found")

    school = request.tenant

    context = {
        'school': school,
        'page_title': f'About {school.name}'
    }

    return render(request, 'core/about.html', context)
