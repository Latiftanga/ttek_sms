from django.shortcuts import render
from .models import School, Region, District


def public_home(request):
    """Public landing page for the TTEK SMS platform."""
    school_count = School.objects.count()
    region_count = Region.objects.count()
    district_count = District.objects.count()

    # Get recent schools (latest 6)
    recent_schools = School.objects.order_by('-created_on')[:6]

    # Features for the platform
    features = [
        {
            'icon': 'fa-users',
            'title': 'Student Management',
            'description': 'Complete student records, enrollment, and guardian management with photo profiles.'
        },
        {
            'icon': 'fa-chalkboard-teacher',
            'title': 'Teacher Portal',
            'description': 'Dedicated dashboards for teachers with class management and gradebook access.'
        },
        {
            'icon': 'fa-graduation-cap',
            'title': 'Academics',
            'description': 'Academic year, term, class, and subject management with timetable scheduling.'
        },
        {
            'icon': 'fa-chart-line',
            'title': 'Gradebook & Reports',
            'description': 'Comprehensive assessment tracking with automated report cards and transcripts.'
        },
        {
            'icon': 'fa-calendar-check',
            'title': 'Attendance Tracking',
            'description': 'Daily attendance recording with class summaries and term reports integration.'
        },
        {
            'icon': 'fa-money-bill-wave',
            'title': 'Finance Management',
            'description': 'Fee setup, billing, payments, and financial reports for school accounting.'
        },
        {
            'icon': 'fa-envelope',
            'title': 'Communications',
            'description': 'SMS notifications to parents and staff with customizable message templates.'
        },
        {
            'icon': 'fa-shield-alt',
            'title': 'Multi-tenant Security',
            'description': 'Complete data isolation between schools with role-based access control.'
        },
    ]

    context = {
        'school_count': school_count,
        'region_count': region_count,
        'district_count': district_count,
        'recent_schools': recent_schools,
        'features': features,
    }
    return render(request, 'schools/public_home.html', context)
