from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_http_methods
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from .models import School, Teacher, Student

User = get_user_model()


def home_view(request):
    """
    Smart router that directs users to the appropriate home page
    based on domain context and authentication status
    """
    # School domain: redirect to school home page
    if getattr(request, 'is_school_domain', False):
        return school_home_view(request)
    
    # Main domain or localhost: show developer portal directly
    return developer_portal_view(request)

def school_home_view(request):
    """
    School-specific home page - for school domains only
    This is what schools see when they visit their domain
    """
    # Security: Only allow on school domains
    if not getattr(request, 'is_school_domain', False):
        return redirect('home')
    
    school = getattr(request, 'tenant', None)
    if not school:
        raise Http404("School not found")

    # If user is already logged in, redirect to dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')

    # Calculate school-specific stats (public info)
    total_students = Student.objects.filter(school=school, is_active=True).count()
    total_teachers = Teacher.objects.filter(school=school, is_active=True).count()
    
    context = {
        'current_school': school,
        'total_students': total_students,
        'total_teachers': total_teachers,
        'page_title': f'{school.name} - Portal',
        'is_school_portal': True,
        'show_login_button': True
    }
    return render(request, 'core/school_home.html', context)



def system_overview_view(request):
    """
    Enhanced system overview page with comprehensive school information
    """
    # Security: Block access from school domains
    if getattr(request, 'is_school_domain', False):
        raise Http404("Page not found")
    
    # Require authentication and superuser status
    if not request.user.is_authenticated or not request.user.is_superuser:
        messages.error(request, 'Access denied. System administrator privileges required.')
        return redirect('home')
    
    # Get all schools with related data for better performance
    schools = School.objects.filter(is_active=True).prefetch_related(
        'students', 'teachers'
    ).order_by('name')
    
    # Calculate comprehensive statistics
    total_schools = schools.count()
    total_students = Student.objects.filter(is_active=True).count()
    total_teachers = Teacher.objects.filter(is_active=True).count()
    
    # Active vs Inactive schools
    active_schools = School.objects.filter(is_active=True).count()
    inactive_schools = School.objects.filter(is_active=False).count()
    
    # Domain configuration stats
    schools_with_custom_domain = School.objects.filter(
        is_active=True, 
        domain__isnull=False
    ).exclude(domain='').count()
    
    schools_with_subdomain = School.objects.filter(
        is_active=True, 
        subdomain__isnull=False
    ).exclude(subdomain='').count()
    
    unconfigured_schools = School.objects.filter(
        is_active=True, 
        domain__isnull=True, 
        subdomain__isnull=True
    ).count() + School.objects.filter(
        is_active=True, 
        domain='', 
        subdomain=''
    ).count()
    
    # Recent activity
    recent_schools = School.objects.filter(
        is_active=True
    ).order_by('-created_at')[:5]
    
    # Students and teachers with accounts
    students_with_accounts = Student.objects.filter(
        is_active=True, 
        user__isnull=False
    ).count()
    
    teachers_with_accounts = Teacher.objects.filter(
        is_active=True, 
        user__isnull=False
    ).count()
    
    # Calculate growth metrics (last 30 days)
    from datetime import datetime, timedelta
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    new_schools_last_month = School.objects.filter(
        created_at__gte=thirty_days_ago
    ).count()
    
    new_students_last_month = Student.objects.filter(
        created_at__gte=thirty_days_ago,
        is_active=True
    ).count()
    
    new_teachers_last_month = Teacher.objects.filter(
        created_at__gte=thirty_days_ago,
        is_active=True
    ).count()

    context = {
        'schools': schools,
        'total_schools': total_schools,
        'active_schools': active_schools,
        'inactive_schools': inactive_schools,
        'total_students': total_students,
        'total_teachers': total_teachers,
        'students_with_accounts': students_with_accounts,
        'teachers_with_accounts': teachers_with_accounts,
        'schools_with_custom_domain': schools_with_custom_domain,
        'schools_with_subdomain': schools_with_subdomain,
        'unconfigured_schools': unconfigured_schools,
        'recent_schools': recent_schools,
        'new_schools_last_month': new_schools_last_month,
        'new_students_last_month': new_students_last_month,
        'new_teachers_last_month': new_teachers_last_month,
        'current_year': timezone.now().year,
        'page_title': 'TTEK SMS - System Overview',
        'show_school_selection': True,
        'is_main_portal': True,
        'is_developer_area': True,
        # System health score (percentage)
        'system_health_score': round(
            ((total_schools - unconfigured_schools) / max(total_schools, 1)) * 100, 1
        ) if total_schools > 0 else 100,
    }
    return render(request, 'core/system_overview.html', context)


def developer_portal_view(request):
    """
    Developer portal - main entry point for system administration
    Handles both authentication and dashboard functionality
    """
    # Security: Block access from school domains
    if getattr(request, 'is_school_domain', False):
        raise Http404("Page not found")
    
    # Handle unauthenticated users
    if not request.user.is_authenticated:
        if request.method == 'POST':
            # Handle login form submission
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            
            if username and password:
                user = authenticate(request, username=username, password=password)
                if user and user.is_active and user.is_superuser:
                    login(request, user)
                    messages.success(request, 'Welcome to the developer portal!')
                    return redirect('home')
                else:
                    messages.error(request, 'Invalid credentials or insufficient permissions.')
            else:
                messages.error(request, 'Please enter both username and password.')
        
        # Show login form for unauthenticated users
        context = {
            'page_title': 'TTEK SMS - Developer Access',
            'show_login_form': True,
            'is_developer_portal': True
        }
        return render(request, 'core/developer_login.html', context)
    
    # Check superuser status for authenticated users
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Developer privileges required.')
        logout(request)
        return redirect('home')

    # Show developer dashboard for authenticated superusers
    total_schools = School.objects.count()
    total_users = User.objects.count()
    total_students = Student.objects.filter(is_active=True).count()
    total_teachers = Teacher.objects.filter(is_active=True).count()
    
    # Recent activity
    recent_schools = School.objects.order_by('-created_at')[:10]
    
    # System health checks
    unconfigured_schools = School.objects.filter(
        is_active=True, 
        domain__isnull=True, 
        subdomain__isnull=True
    ).count()

    context = {
        'total_schools': total_schools,
        'total_users': total_users,
        'total_students': total_students,
        'total_teachers': total_teachers,
        'recent_schools': recent_schools,
        'unconfigured_schools': unconfigured_schools,
        'page_title': 'Developer Portal - TTEK SMS',
        'is_developer_portal': True,
        'show_dashboard': True
    }
    return render(request, 'core/developer_portal.html', context)



def school_setup_view(request):
    """
    Setup page when no schools exist
    """
    # Check if schools already exist
    if School.objects.filter(is_active=True).exists():
        return redirect('home')

    # Check if user is superuser
    if not (request.user.is_authenticated and request.user.is_superuser):
        context = {
            'page_title': 'System Setup Required'
        }
        return render(request, 'core/setup_required.html', context)

    # Show setup page for superuser
    context = {
        'page_title': 'School Management System - Initial Setup'
    }
    return render(request, 'core/school_setup.html', context)


def school_login_view(request):
    """Enhanced login view with domain-aware logic"""
    
    # Handle different domain contexts
    if getattr(request, 'is_school_domain', False):
        # School domain - get tenant from middleware
        school = getattr(request, 'tenant', None)
        if not school:
            raise Http404("School not found")
    elif getattr(request, 'is_localhost', False):
        # Localhost - handle school selection
        school_id = request.GET.get('school')
        if school_id:
            try:
                school = School.objects.get(id=school_id, is_active=True)
            except School.DoesNotExist:
                messages.error(request, 'Selected school not found.')
                return redirect('home')
        else:
            # No school selected on localhost
            schools_count = School.objects.filter(is_active=True).count()
            if schools_count == 0:
                return redirect('school_setup')
            elif schools_count == 1:
                school = School.objects.filter(is_active=True).first()
            else:
                messages.info(request, 'Please select a school to continue.')
                return redirect('home')
    else:
        # Main domain - shouldn't reach here normally
        return redirect('home')

    # If user is already authenticated, redirect to dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            messages.error(request, 'Please enter both username and password.')
        else:
            user = authenticate(request, username=username, password=password)

            if user and user.is_active:
                # Check if user belongs to this school
                user_school = user.get_school()
                if user_school and user_school.id == school.id:
                    login(request, user)
                    messages.success(request, f'Welcome to {school.name}!')
                    return redirect('core:dashboard')
                else:
                    messages.error(request, 'You are not authorized to access this school.')
            else:
                messages.error(request, 'Invalid username or password.')

    context = {
        'current_school': school,
        'page_title': f'{school.name} - Login',
        'show_back_to_selection': getattr(request, 'is_localhost', False),
        'is_school_login': True
    }
    return render(request, 'core/login.html', context)


@login_required
def dashboard_view(request):
    """Role-based dashboard view"""
    user = request.user
    school = getattr(request, 'tenant', None) or user.get_school()

    # Determine user role and show appropriate dashboard
    if user.is_admin:
        return admin_dashboard(request, school)
    elif user.is_teacher:
        return teacher_dashboard(request, school)
    elif user.is_student:
        return student_dashboard(request, school)
    else:
        messages.error(request, 'Access denied.')
        return redirect('login')


def admin_dashboard(request, school):
    """Admin dashboard with school statistics"""
    if school:
        total_students = Student.objects.filter(
            school=school, is_active=True).count()
        total_teachers = Teacher.objects.filter(
            school=school, is_active=True).count()
        students_with_accounts = Student.objects.filter(
            school=school, is_active=True, user__isnull=False
        ).count()
        teachers_with_accounts = Teacher.objects.filter(
            school=school, is_active=True, user__isnull=False
        ).count()

        recent_students = Student.objects.filter(
            school=school, is_active=True
        ).order_by('-created_at')[:10]

        recent_teachers = Teacher.objects.filter(
            school=school, is_active=True
        ).order_by('-created_at')[:5]
    else:
        total_students = total_teachers = students_with_accounts = teachers_with_accounts = 0
        recent_students = recent_teachers = []

    context = {
        'user_role': 'Admin',
        'dashboard_type': 'admin',
        'stats': {
            'total_students': total_students,
            'total_teachers': total_teachers,
            'students_with_accounts': students_with_accounts,
            'teachers_with_accounts': teachers_with_accounts,
        },
        'recent_students': recent_students,
        'recent_teachers': recent_teachers,
        'current_school': school,
        'page_title': f'{school.name if school else "Admin"} - Dashboard'
    }
    return render(request, 'core/dashboard.html', context)


def teacher_dashboard(request, school):
    """Teacher dashboard"""
    try:
        teacher_profile = request.user.teacher_profile
        subjects = teacher_profile.subjects or []
    except AttributeError:
        teacher_profile = None
        subjects = []

    context = {
        'user_role': 'Teacher',
        'dashboard_type': 'teacher',
        'teacher_profile': teacher_profile,
        'subjects': subjects,
        'current_school': school,
        'page_title': f'{school.name if school else "Teacher"} - Dashboard'
    }
    return render(request, 'core/dashboard.html', context)


def student_dashboard(request, school):
    """Student dashboard"""
    try:
        student_profile = request.user.student_profile
    except AttributeError:
        student_profile = None

    context = {
        'user_role': 'Student',
        'dashboard_type': 'student',
        'student_profile': student_profile,
        'current_school': school,
        'page_title': f'{school.name if school else "Student"} - Dashboard'
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def logout_view(request):
    """
    Custom logout view that redirects users back to their school's login page
    """
    # Get the school context BEFORE logging out the user
    school = None

    # Method 1: Get school from current tenant (domain-based)
    if hasattr(request, 'tenant') and request.tenant:
        school = request.tenant

    # Method 2: Get school from user profile (fallback)
    elif request.user.is_authenticated:
        try:
            school = request.user.get_school()
        except:
            school = None

    # Method 3: Handle localhost with school parameter
    if not school and getattr(request, 'is_localhost', False):
        school_id = request.GET.get('school')
        if school_id:
            try:
                school = School.objects.get(id=school_id, is_active=True)
            except School.DoesNotExist:
                pass

    # Perform logout
    logout(request)
    messages.success(request, 'You have been logged out successfully.')

    # Determine redirect URL based on domain context
    if getattr(request, 'is_school_domain', False) and school:
        # School domain: redirect to school's login page
        return redirect('core:login')

    elif getattr(request, 'is_localhost', False) and school:
        # Localhost: redirect to login with school parameter
        return redirect(f"{reverse('core:login')}?school={school.id}")

    elif getattr(request, 'is_main_domain', False):
        # Main domain: redirect to home (which shows developer portal)
        return redirect('core:home')

    else:
        # Fallback: try to redirect to login or home
        if school:
            return redirect('core:login')
        else:
            return redirect('core:home')
