from core.models import School, User
from django.db.models import Q


class DashboardService:
    """Service class for dashboard-related operations"""

    @staticmethod
    def get_school_stats(school):
        """Get statistics for a specific school"""
        if not school:
            return {}

        # Get user counts for the school
        users = User.objects.filter(
            Q(student_profile__school=school) |
            Q(teacher_profile__school=school) |
            Q(admin_profile__school=school)
        )

        stats = {
            'total_students': users.filter(is_student=True, is_active=True).count(),
            'total_teachers': users.filter(is_teacher=True, is_active=True).count(),
            'total_classes': 0,  # Placeholder for future implementation
            'total_subjects': 0,  # Placeholder for future implementation
        }

        return stats

    @staticmethod
    def get_recent_activities(school, limit=10):
        """Get recent activities for a school"""
        # Placeholder for future implementation
        activities = [
            {
                'action': 'Student Registration',
                'description': 'New student Amina Mohammed registered',
                'time': '2 hours ago',
                'icon': 'fas fa-user-plus',
                'type': 'success'
            },
            {
                'action': 'Teacher Assignment',
                'description': 'Mr. Kwame assigned to Mathematics',
                'time': '4 hours ago',
                'icon': 'fas fa-chalkboard-teacher',
                'type': 'info'
            },
            {
                'action': 'Class Created',
                'description': 'SHS 1A class created',
                'time': '1 day ago',
                'icon': 'fas fa-door-open',
                'type': 'warning'
            }
        ]

        return activities[:limit]

    @staticmethod
    def get_superuser_schools():
        """Get all schools for superuser dashboard"""
        return School.objects.filter(is_active=True).order_by('name')
