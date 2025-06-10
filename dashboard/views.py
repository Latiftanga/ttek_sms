"""
Dashboard views for the school management system
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from core.models import School, User
from core.middleware import SchoolFilterMixin
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    Main dashboard view showing school statistics and recent activity
    """
    template_name = 'dashboard/index.html'

    def dispatch(self, request, *args, **kwargs):
        """Check if user has school access and proper domain"""
        # Handle admin portal access
        if getattr(request, 'is_admin_portal', False):
            if not request.user.is_superuser:
                messages.error(
                    request, 'Access denied. Admin portal requires superuser privileges.')
                return redirect('auth:login')
            return super().dispatch(request, *args, **kwargs)

        # Handle school portal access
        if not hasattr(request, 'school') or not request.school:
            messages.error(
                request, 'Access denied. No school found for this domain.')
            return redirect('auth:login')

        # Check if user belongs to this school (unless superuser)
        if not request.user.is_superuser:
            user_school = request.user.get_school()
            if not user_school:
                messages.error(
                    request, 'Your account is not associated with any school.')
                return redirect('auth:login')

            if user_school != request.school:
                # Redirect to user's correct school domain
                return redirect(user_school.get_portal_url() + request.get_full_path())

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get user and request info
        user = self.request.user
        is_admin_portal = getattr(self.request, 'is_admin_portal', False)
        school = getattr(self.request, 'school', None)

        # Base context
        context.update({
            'is_admin_portal': is_admin_portal,
            'current_domain': self.request.get_host(),
            'user_role': user.get_role_display(),
            'user_profile': user.get_profile(),
        })

        if is_admin_portal:
            # Admin portal view - show system-wide stats
            all_schools = School.objects.filter(is_active=True)
            context.update({
                'total_schools': all_schools.count(),
                'verified_schools': all_schools.filter(domain_verified=True).count(),
                'pending_schools': all_schools.filter(domain_verified=False).count(),
                'recent_schools': all_schools.order_by('-created_at')[:5],
                'total_users': User.objects.count(),
                'active_users': User.objects.filter(is_active=True).count(),
            })

        elif school:
            # School portal view - show school-specific stats
            context.update({
                'school': school,
                'total_students': school.get_student_count(),
                'total_teachers': school.get_teacher_count(),
                'school_name': school.name,
                'school_code': school.code,
                'school_domain': school.domain,
                'custom_domain': school.custom_domain,
                'domain_verified': school.domain_verified,
            })

            # Get recent students (placeholder - will be implemented in Phase 2)
            context['recent_students'] = []

            # Get recent activity (placeholder with school context)
            context['recent_activity'] = [
                {
                    'action': 'Student registered',
                    'description': f'New student was registered at {school.name}',
                    'time': timezone.now() - timedelta(hours=2),
                    'icon': 'fas fa-user-plus',
                    'color': 'success'
                },
                {
                    'action': 'Grade updated',
                    'description': f'Mathematics grades updated for SHS 2A',
                    'time': timezone.now() - timedelta(hours=5),
                    'icon': 'fas fa-chart-line',
                    'color': 'info'
                },
                {
                    'action': 'Teacher added',
                    'description': f'New teacher joined {school.name}',
                    'time': timezone.now() - timedelta(days=1),
                    'icon': 'fas fa-chalkboard-teacher',
                    'color': 'primary'
                },
            ]

            # Quick stats for cards
            context['stats'] = {
                'students': {
                    'total': context['total_students'],
                    'active': context['total_students'],  # Placeholder
                    'new_this_month': 0,  # Placeholder
                },
                'teachers': {
                    'total': context['total_teachers'],
                    'active': context['total_teachers'],  # Placeholder
                },
                'classes': {
                    'total': 0,  # Placeholder - will implement in Phase 2
                },
                'subjects': {
                    'total': 0,  # Placeholder - will implement in Phase 2
                }
            }

        return context


@login_required
def dashboard_index(request):
    """
    Function-based view for dashboard (alternative to class-based view)
    """
    # Check user permissions
    if not request.user.is_superuser and not hasattr(request, 'school'):
        messages.error(request, 'Access denied. No school association found.')
        return redirect('auth:login')

    school = getattr(request, 'school', None)

    context = {
        'school': school,
        'user_role': request.user.get_role_display(),
        'user_profile': request.user.get_profile(),
    }

    if school:
        context.update({
            'total_students': school.get_student_count(),
            'total_teachers': school.get_teacher_count(),
            'school_name': school.name,
        })

    return render(request, 'dashboard/index.html', context)


@login_required
def quick_stats_view(request):
    """
    AJAX view for quick statistics
    """
    school = getattr(request, 'school', None)

    if not school:
        return JsonResponse({'error': 'No school context'}, status=400)

    stats = {
        'students': school.get_student_count(),
        'teachers': school.get_teacher_count(),
        'classes': 0,  # Placeholder
        'subjects': 0,  # Placeholder
    }

    return JsonResponse(stats)
