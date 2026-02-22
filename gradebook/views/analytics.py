from collections import defaultdict, Counter
import json
import logging

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django_ratelimit.decorators import ratelimit

from .base import admin_required, htmx_render
from ..models import GradingSystem, SubjectTermGrade, TermReport
from .. import config
from academics.models import Class
from core.models import Term

logger = logging.getLogger(__name__)


# ============ Analytics Dashboard ============

@login_required
@admin_required
@ratelimit(key='user', rate='60/h', block=True)
def analytics(request):
    """Analytics dashboard with grade trends and statistics (Admin only)."""
    current_term = Term.get_current()
    classes = Class.objects.filter(is_active=True).order_by('level_number', 'name')

    # Get filter parameters
    class_id = request.GET.get('class')
    selected_class = None

    if class_id:
        selected_class = get_object_or_404(Class, pk=class_id)

    class_options = [(c.pk, c.name) for c in classes]
    analytics_class_attrs = {
        'hx-target': '#class-analytics-content',
        'hx-swap': 'innerHTML',
        'hx-trigger': "change[this.value != '']",
        'hx-on::before-request': "event.detail.path = '/gradebook/analytics/class/' + this.value + '/'",
    }

    context = {
        'current_term': current_term,
        'classes': classes,
        'class_options': class_options,
        'analytics_class_attrs': analytics_class_attrs,
        'selected_class': selected_class,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Gradebook', 'url': '/gradebook/'},
            {'label': 'Analytics'},
        ],
    }

    return htmx_render(
        request,
        'gradebook/analytics.html',
        'gradebook/partials/analytics_content.html',
        context
    )


@login_required
@admin_required
@ratelimit(key='user', rate='60/h', block=True)
def analytics_class_data(request, class_id):
    """Get analytics data for a specific class (HTMX partial)."""
    current_term = Term.get_current()
    class_obj = get_object_or_404(Class, pk=class_id)

    if not current_term:
        return render(request, 'gradebook/partials/analytics_class.html', {
            'error': 'No current term set'
        })

    # Get grading system based on class level
    grading_level = 'SHS' if class_obj.level_type == 'shs' else 'BASIC'
    grading_system = GradingSystem.objects.filter(
        level=grading_level,
        is_active=True
    ).first()

    # Use grading system thresholds or defaults
    pass_mark = grading_system.pass_mark if grading_system else config.DEFAULT_PASS_MARK
    if grading_system:
        min_avg_for_promotion = grading_system.min_average_for_promotion
    else:
        min_avg_for_promotion = config.DEFAULT_MIN_AVERAGE_FOR_PROMOTION

    # Get all term reports for this class
    term_reports = list(TermReport.objects.filter(
        student__current_class=class_obj,
        term=current_term
    ).select_related('student').order_by('-average'))

    # Get subject grades for grade distribution
    subject_grades = list(SubjectTermGrade.objects.filter(
        student__current_class=class_obj,
        term=current_term,
        total_score__isnull=False
    ).select_related('subject', 'student'))

    # Calculate statistics
    stats = calculate_class_stats(term_reports, subject_grades)

    # Get subject performance comparison (using configurable pass mark)
    subject_performance = calculate_subject_performance(subject_grades, pass_mark=pass_mark)

    # Get grade distribution
    grade_distribution = calculate_grade_distribution(subject_grades)

    # Get top performers
    top_performers = term_reports[:config.TOP_PERFORMERS_LIMIT] if term_reports else []

    # Get students needing attention (failed 2+ subjects or avg below promotion threshold)
    at_risk = [
        r for r in term_reports
        if r.subjects_failed >= 2 or (r.average and r.average < min_avg_for_promotion)
    ][:config.AT_RISK_STUDENTS_LIMIT]

    context = {
        'class_obj': class_obj,
        'current_term': current_term,
        'stats': stats,
        'subject_performance': subject_performance,
        'grade_distribution': grade_distribution,
        'grade_distribution_json': json.dumps(grade_distribution),
        'subject_performance_json': json.dumps(subject_performance),
        'top_performers': top_performers,
        'at_risk_students': at_risk,
        'total_students': len(term_reports),
        'grading_system': grading_system,
        'pass_mark': pass_mark,
    }

    return render(request, 'gradebook/partials/analytics_class.html', context)


@login_required
@admin_required
@ratelimit(key='user', rate='60/h', block=True)
def analytics_overview(request):
    """School-wide analytics overview (HTMX partial, Admin only)."""
    current_term = Term.get_current()

    if not current_term:
        return render(request, 'gradebook/partials/analytics_overview.html', {
            'error': 'No current term set'
        })

    # Get default pass mark from any active grading system (school-wide stats)
    default_grading_system = GradingSystem.objects.filter(is_active=True).first()
    default_pass_mark = default_grading_system.pass_mark if default_grading_system else config.DEFAULT_PASS_MARK

    # Get all class stats in a single grouped query (avoids N+1 per class)
    class_report_stats = TermReport.objects.filter(
        term=current_term,
        student__current_class__is_active=True
    ).values(
        'student__current_class', 'student__current_class__name',
        'student__current_class__level_number'
    ).annotate(
        avg_score=Avg('average'),
        total_students=Count('id'),
        passed=Count('id', filter=Q(subjects_failed=0)),
    ).filter(total_students__gt=0).order_by('-avg_score')

    class_stats = []
    for row in class_report_stats:
        total = row['total_students']
        passed = row['passed']
        # Use a simple namespace so template can access stat.class.name
        class_obj = type('ClassInfo', (), {'name': row['student__current_class__name']})()
        class_stats.append({
            'class': class_obj,
            'average': round(row['avg_score'] or 0, 1),
            'total_students': total,
            'passed': passed,
            'pass_rate': round((passed / total) * 100, 1) if total > 0 else 0,
        })

    # Overall school stats
    all_reports = TermReport.objects.filter(term=current_term)
    school_stats = all_reports.aggregate(
        total_students=Count('id'),
        avg_score=Avg('average'),
        total_passed=Count('id', filter=Q(subjects_failed=0)),
    )

    # Subject-wise school performance (using configurable pass mark)
    subject_stats = SubjectTermGrade.objects.filter(
        term=current_term,
        total_score__isnull=False
    ).values('subject__name', 'subject__short_name').annotate(
        avg_score=Avg('total_score'),
        students=Count('id'),
        passed=Count('id', filter=Q(total_score__gte=default_pass_mark)),
    ).order_by('-avg_score')[:config.TOP_SUBJECTS_LIMIT]

    context = {
        'current_term': current_term,
        'class_stats': class_stats,
        'class_stats_json': json.dumps([
            {'name': s['class'].name, 'average': float(s['average'])}
            for s in class_stats
        ]),
        'school_stats': {
            'total_students': school_stats['total_students'] or 0,
            'average': round(school_stats['avg_score'] or 0, 1),
            'passed': school_stats['total_passed'] or 0,
            'pass_rate': round(
                (school_stats['total_passed'] / school_stats['total_students']) * 100, 1
            ) if school_stats['total_students'] else 0,
        },
        'subject_stats': list(subject_stats),
        'pass_mark': default_pass_mark,
    }

    return render(request, 'gradebook/partials/analytics_overview.html', context)


@login_required
@admin_required
@ratelimit(key='user', rate='60/h', block=True)
def analytics_term_comparison(request):
    """Compare performance across terms (HTMX partial, Admin only)."""
    # Get all terms from current academic year
    current_term = Term.get_current()
    if not current_term:
        return render(request, 'gradebook/partials/analytics_terms.html', {
            'error': 'No current term set'
        })

    terms = Term.objects.filter(
        academic_year=current_term.academic_year
    ).order_by('term_number')

    term_data = []
    for term in terms:
        stats = TermReport.objects.filter(term=term).aggregate(
            avg_score=Avg('average'),
            total_students=Count('id'),
            passed=Count('id', filter=Q(subjects_failed=0)),
        )

        if stats['total_students'] > 0:
            term_data.append({
                'term': term,
                'average': round(stats['avg_score'] or 0, 1),
                'total_students': stats['total_students'],
                'passed': stats['passed'],
                'pass_rate': round((stats['passed'] / stats['total_students']) * 100, 1),
            })

    context = {
        'terms': term_data,
        'terms_json': json.dumps([
            {'name': t['term'].name, 'average': float(t['average']), 'pass_rate': float(t['pass_rate'])}
            for t in term_data
        ]),
        'current_term': current_term,
    }

    return render(request, 'gradebook/partials/analytics_terms.html', context)


# ============ Analytics Helper Functions ============

def calculate_class_stats(term_reports, subject_grades):
    """Calculate comprehensive class statistics."""
    if not term_reports:
        return {
            'average': 0,
            'highest': 0,
            'lowest': 0,
            'pass_rate': 0,
            'subjects_avg_passed': 0,
        }

    averages = [r.average for r in term_reports if r.average is not None]

    if not averages:
        return {
            'average': 0,
            'highest': 0,
            'lowest': 0,
            'pass_rate': 0,
            'subjects_avg_passed': 0,
        }

    total_students = len(term_reports)
    passed = sum(1 for r in term_reports if r.subjects_failed == 0)
    avg_subjects_passed = sum(r.subjects_passed for r in term_reports) / total_students if total_students else 0

    return {
        'average': round(sum(averages) / len(averages), 1),
        'highest': round(max(averages), 1),
        'lowest': round(min(averages), 1),
        'pass_rate': round((passed / total_students) * 100, 1) if total_students else 0,
        'subjects_avg_passed': round(avg_subjects_passed, 1),
    }


def calculate_subject_performance(subject_grades, pass_mark=None):
    """
    Calculate per-subject performance metrics.

    Args:
        subject_grades: List of SubjectTermGrade objects
        pass_mark: The pass mark threshold (defaults to grading system standard)
    """
    if pass_mark is None:
        pass_mark = config.DEFAULT_PASS_MARK

    subject_data = defaultdict(lambda: {'scores': [], 'passed': 0, 'total': 0})

    for grade in subject_grades:
        subj = grade.subject.short_name or grade.subject.name[:10]
        subject_data[subj]['scores'].append(float(grade.total_score))
        subject_data[subj]['total'] += 1
        if grade.total_score >= pass_mark:
            subject_data[subj]['passed'] += 1

    result = []
    for name, data in subject_data.items():
        if data['scores']:
            result.append({
                'name': name,
                'average': round(sum(data['scores']) / len(data['scores']), 1),
                'pass_rate': round((data['passed'] / data['total']) * 100, 1) if data['total'] else 0,
                'students': data['total'],
            })

    # Sort by average descending
    result.sort(key=lambda x: x['average'], reverse=True)
    return result


def calculate_grade_distribution(subject_grades, grading_system=None):
    """Calculate grade distribution across all subjects.

    Args:
        subject_grades: List of SubjectTermGrade objects
        grading_system: Optional GradingSystem to get grade order from.
                       If not provided, fetches the active one.
    """
    grade_counts = Counter(g.grade for g in subject_grades if g.grade)

    # Get grade order from grading system (ordered by min_percentage descending)
    if grading_system is None:
        grading_system = GradingSystem.objects.filter(
            is_active=True
        ).prefetch_related('scales').first()

    if grading_system:
        # Get grades ordered by min_percentage descending (highest grades first)
        grade_order = list(
            grading_system.scales.order_by('-min_percentage')
            .values_list('grade_label', flat=True)
        )
        # Determine key grades (first, middle, pass threshold, and last)
        key_grades = set()
        if grade_order:
            key_grades.add(grade_order[0])  # Best grade
            key_grades.add(grade_order[-1])  # Worst grade
            if len(grade_order) > 2:
                key_grades.add(grade_order[len(grade_order) // 2])  # Middle grade
    else:
        # Fallback to WASSCE grades if no grading system configured
        grade_order = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']
        key_grades = {'A1', 'B2', 'C6', 'F9'}

    result = []
    for grade in grade_order:
        count = grade_counts.get(grade, 0)
        if count > 0 or grade in key_grades:
            result.append({
                'grade': grade,
                'count': count,
            })

    return result
