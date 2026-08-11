from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.db import models
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from io import StringIO

from django.core.management import call_command

from .models import (
    GradingSystem, GradeScale, AssessmentCategory,
    Assignment, Score, SubjectTermGrade, TermReport, RemarkTemplate
)
from .forms import GradeScaleForm, AssessmentCategoryForm, ScoreForm
from .utils import compute_term_attendance_stats
from academics.models import (
    Subject, Class, Programme, ClassSubject, StudentSubjectEnrollment,
    AttendanceSession, AttendanceRecord, Period, TimetableEntry,
)
from core.models import AcademicYear, Term
from students.models import Student, Guardian, Enrollment


User = get_user_model()


class GradebookTenantTestCase(TenantTestCase):
    """Base test case for gradebook tests with tenant support."""

    @classmethod
    def setup_tenant(cls, tenant):
        """Called when tenant is created."""
        tenant.name = 'Test School'
        tenant.short_name = 'TEST'

    def setUp(self):
        """Set up test client."""
        super().setUp()
        self.client = TenantClient(self.tenant)


class GradingSystemModelTest(GradebookTenantTestCase):
    """Tests for GradingSystem model."""

    def setUp(self):
        super().setUp()
        self.grading_system = GradingSystem.objects.create(
            name='WASSCE',
            level='SHS',
            pass_mark=Decimal('40.00'),
            credit_mark=Decimal('50.00'),
            aggregate_subjects_count=6,
            min_subjects_to_pass=6,
            min_average_for_promotion=Decimal('45.00'),
            require_core_pass=True
        )

    def test_grading_system_creation(self):
        """Test GradingSystem can be created."""
        self.assertEqual(self.grading_system.name, 'WASSCE')
        self.assertEqual(self.grading_system.level, 'SHS')
        self.assertTrue(self.grading_system.is_active)

    def test_is_passing_score(self):
        """Test pass mark check."""
        self.assertTrue(self.grading_system.is_passing_score(50))
        self.assertTrue(self.grading_system.is_passing_score(40))
        self.assertFalse(self.grading_system.is_passing_score(39))
        self.assertFalse(self.grading_system.is_passing_score(None))

    def test_is_credit_score(self):
        """Test credit mark check."""
        self.assertTrue(self.grading_system.is_credit_score(60))
        self.assertTrue(self.grading_system.is_credit_score(50))
        self.assertFalse(self.grading_system.is_credit_score(49))

    def test_str_representation(self):
        """Test string representation."""
        self.assertEqual(str(self.grading_system), 'WASSCE (Senior High School)')


class GradeScaleModelTest(GradebookTenantTestCase):
    """Tests for GradeScale model."""

    def setUp(self):
        super().setUp()
        self.grading_system = GradingSystem.objects.create(
            name='WASSCE',
            level='SHS'
        )
        self.grade_a1 = GradeScale.objects.create(
            grading_system=self.grading_system,
            grade_label='A1',
            min_percentage=Decimal('80.00'),
            max_percentage=Decimal('100.00'),
            aggregate_points=1,
            interpretation='Excellent',
            is_pass=True,
            is_credit=True,
            order=1
        )
        self.grade_f9 = GradeScale.objects.create(
            grading_system=self.grading_system,
            grade_label='F9',
            min_percentage=Decimal('0.00'),
            max_percentage=Decimal('39.99'),
            aggregate_points=9,
            interpretation='Fail',
            is_pass=False,
            is_credit=False,
            order=9
        )

    def test_grade_scale_creation(self):
        """Test GradeScale can be created."""
        self.assertEqual(self.grade_a1.grade_label, 'A1')
        self.assertEqual(self.grade_a1.aggregate_points, 1)

    def test_get_grade_for_score(self):
        """Test looking up grade for a score."""
        grade = self.grading_system.get_grade_for_score(85)
        self.assertEqual(grade.grade_label, 'A1')

        grade = self.grading_system.get_grade_for_score(30)
        self.assertEqual(grade.grade_label, 'F9')

    def test_str_representation(self):
        """Test string representation."""
        self.assertIn('A1', str(self.grade_a1))
        self.assertIn('80', str(self.grade_a1))


class AssessmentCategoryModelTest(GradebookTenantTestCase):
    """Tests for AssessmentCategory model."""

    def setUp(self):
        super().setUp()
        self.class_score = AssessmentCategory.objects.create(
            name='Class Score',
            short_name='CA',
            percentage=30,
            order=1
        )
        self.exam = AssessmentCategory.objects.create(
            name='Examination',
            short_name='EXAM',
            percentage=70,
            order=2
        )

    def test_category_creation(self):
        """Test AssessmentCategory can be created."""
        self.assertEqual(self.class_score.name, 'Class Score')
        self.assertEqual(self.class_score.percentage, 30)

    def test_total_percentage(self):
        """Test total percentage equals 100."""
        total = AssessmentCategory.objects.filter(is_active=True).aggregate(
            total=models.Sum('percentage')
        )['total']
        self.assertEqual(total, 100)

    def test_str_representation(self):
        """Test string representation."""
        self.assertEqual(str(self.class_score), 'Class Score (30%)')


class GradeScaleFormTest(GradebookTenantTestCase):
    """Tests for GradeScaleForm."""

    def setUp(self):
        super().setUp()
        self.grading_system = GradingSystem.objects.create(
            name='WASSCE',
            level='SHS'
        )

    def test_valid_form(self):
        """Test form with valid data."""
        form = GradeScaleForm(
            data={
                'grade_label': 'A1',
                'min_percentage': 80,
                'max_percentage': 100,
                'aggregate_points': 1,
                'interpretation': 'Excellent',
                'is_pass': True,
                'is_credit': True,
                'order': 1
            },
            grading_system=self.grading_system
        )
        self.assertTrue(form.is_valid())

    def test_min_greater_than_max_invalid(self):
        """Test form rejects min > max."""
        form = GradeScaleForm(
            data={
                'grade_label': 'A1',
                'min_percentage': 100,
                'max_percentage': 80,
                'aggregate_points': 1,
                'interpretation': 'Excellent',
                'is_pass': True,
                'is_credit': True,
                'order': 1
            },
            grading_system=self.grading_system
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Minimum percentage cannot be greater than maximum percentage', str(form.errors))

    def test_percentage_out_of_range_invalid(self):
        """Test form rejects percentages outside 0-100."""
        form = GradeScaleForm(
            data={
                'grade_label': 'A1',
                'min_percentage': -10,
                'max_percentage': 110,
                'aggregate_points': 1,
                'interpretation': 'Excellent',
                'is_pass': True,
                'is_credit': True,
                'order': 1
            },
            grading_system=self.grading_system
        )
        self.assertFalse(form.is_valid())


class AssessmentCategoryFormTest(GradebookTenantTestCase):
    """Tests for AssessmentCategoryForm."""

    def test_valid_form(self):
        """Test form with valid data."""
        form = AssessmentCategoryForm(
            data={
                'name': 'Class Score',
                'short_name': 'ca',
                'category_type': 'CLASS_SCORE',
                'percentage': 30,
                'order': 1,
                'expected_assessments': 0,
                'min_assessments': 0,
                'max_assessments': 0,
                'is_active': True
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_short_name_uppercase(self):
        """Test short_name is converted to uppercase."""
        form = AssessmentCategoryForm(
            data={
                'name': 'Class Score',
                'short_name': 'ca',
                'category_type': 'CLASS_SCORE',
                'percentage': 30,
                'order': 1,
                'expected_assessments': 0,
                'min_assessments': 0,
                'max_assessments': 0,
                'is_active': True
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['short_name'], 'CA')

    def test_percentage_out_of_range_invalid(self):
        """Test form rejects percentage outside 0-100."""
        form = AssessmentCategoryForm(
            data={
                'name': 'Test',
                'short_name': 'T',
                'category_type': 'OTHER',
                'percentage': 150,
                'order': 1,
                'expected_assessments': 0,
                'min_assessments': 0,
                'max_assessments': 0,
                'is_active': True
            }
        )
        self.assertFalse(form.is_valid())

    def test_assessment_count_validation(self):
        """Test min/max assessment count validation."""
        # Min greater than max should fail
        form = AssessmentCategoryForm(
            data={
                'name': 'Test',
                'short_name': 'T',
                'category_type': 'OTHER',
                'percentage': 30,
                'order': 1,
                'expected_assessments': 2,
                'min_assessments': 5,
                'max_assessments': 3,
                'is_active': True
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Minimum assessments cannot be greater than maximum', str(form.errors))


class ScoreFormTest(GradebookTenantTestCase):
    """Tests for ScoreForm."""

    def test_valid_score(self):
        """Test form with valid score."""
        form = ScoreForm(
            data={
                'student_id': 1,
                'assignment_id': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                'points': Decimal('85.5')
            },
            max_points=Decimal('100')
        )
        self.assertTrue(form.is_valid())

    def test_score_exceeds_max_invalid(self):
        """Test form rejects score > max points."""
        form = ScoreForm(
            data={
                'student_id': 1,
                'assignment_id': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                'points': Decimal('105')
            },
            max_points=Decimal('100')
        )
        self.assertFalse(form.is_valid())

    def test_negative_score_invalid(self):
        """Test form rejects negative score."""
        form = ScoreForm(
            data={
                'student_id': 1,
                'assignment_id': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                'points': Decimal('-5')
            },
            max_points=Decimal('100')
        )
        self.assertFalse(form.is_valid())

    def test_decimal_score_valid(self):
        """Test form accepts decimal scores."""
        form = ScoreForm(
            data={
                'student_id': 1,
                'assignment_id': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                'points': Decimal('87.75')
            },
            max_points=Decimal('100')
        )
        self.assertTrue(form.is_valid())


class GradeCalculationTest(GradebookTenantTestCase):
    """Tests for grade calculation logic."""

    def setUp(self):
        super().setUp()
        # Create grading system with full scale
        self.grading_system = GradingSystem.objects.create(
            name='WASSCE',
            level='SHS',
            pass_mark=Decimal('40.00'),
            credit_mark=Decimal('50.00')
        )

        # Create grade scales
        scales = [
            ('A1', 80, 100, 1, 'Excellent', True, True),
            ('B2', 70, 79, 2, 'Very Good', True, True),
            ('B3', 65, 69, 3, 'Good', True, True),
            ('C4', 60, 64, 4, 'Credit', True, True),
            ('C5', 55, 59, 5, 'Credit', True, True),
            ('C6', 50, 54, 6, 'Credit', True, True),
            ('D7', 45, 49, 7, 'Pass', True, False),
            ('E8', 40, 44, 8, 'Pass', True, False),
            ('F9', 0, 39, 9, 'Fail', False, False),
        ]

        for i, (label, min_pct, max_pct, points, interp, is_pass, is_credit) in enumerate(scales):
            GradeScale.objects.create(
                grading_system=self.grading_system,
                grade_label=label,
                min_percentage=Decimal(str(min_pct)),
                max_percentage=Decimal(str(max_pct)),
                aggregate_points=points,
                interpretation=interp,
                is_pass=is_pass,
                is_credit=is_credit,
                order=i + 1
            )

    def test_grade_lookup_a1(self):
        """Test grade lookup for A1."""
        grade = self.grading_system.get_grade_for_score(85)
        self.assertEqual(grade.grade_label, 'A1')
        self.assertEqual(grade.aggregate_points, 1)

    def test_grade_lookup_c6(self):
        """Test grade lookup for C6 (credit boundary)."""
        grade = self.grading_system.get_grade_for_score(50)
        self.assertEqual(grade.grade_label, 'C6')
        self.assertTrue(grade.is_credit)

    def test_grade_lookup_d7(self):
        """Test grade lookup for D7 (pass but no credit)."""
        grade = self.grading_system.get_grade_for_score(47)
        self.assertEqual(grade.grade_label, 'D7')
        self.assertTrue(grade.is_pass)
        self.assertFalse(grade.is_credit)

    def test_grade_lookup_f9(self):
        """Test grade lookup for F9 (fail)."""
        grade = self.grading_system.get_grade_for_score(30)
        self.assertEqual(grade.grade_label, 'F9')
        self.assertFalse(grade.is_pass)


class AggregateCalculationTest(GradebookTenantTestCase):
    """Tests for WASSCE aggregate calculation."""

    def setUp(self):
        super().setUp()
        self.grading_system = GradingSystem.objects.create(
            name='WASSCE',
            level='SHS',
            aggregate_subjects_count=6
        )

        # Create grade scales
        for i, (label, points) in enumerate([
            ('A1', 1), ('B2', 2), ('B3', 3), ('C4', 4),
            ('C5', 5), ('C6', 6), ('D7', 7), ('E8', 8), ('F9', 9)
        ]):
            GradeScale.objects.create(
                grading_system=self.grading_system,
                grade_label=label,
                min_percentage=Decimal('0'),
                max_percentage=Decimal('100'),
                aggregate_points=points,
                order=i + 1
            )

    def test_best_aggregate_perfect(self):
        """Test best possible aggregate (6 A1s = 6)."""
        # This would require actual SubjectTermGrade objects
        # For now, test the grading system configuration
        self.assertEqual(self.grading_system.aggregate_subjects_count, 6)

    def test_aggregate_subjects_count(self):
        """Test aggregate uses correct number of subjects."""
        self.assertEqual(self.grading_system.aggregate_subjects_count, 6)


# ============ Report Cards Status Filter Tests ============


class ReportCardsStatusFilterTestCase(GradebookTenantTestCase):
    """Base test case for report cards status filter tests."""

    def setUp(self):
        """Set up test data."""
        super().setUp()

        # Create admin user
        self.admin_user = User.objects.create_user(
            email='admin@school.com',
            password='testpass123',
            is_school_admin=True
        )

        # Create teacher user (non-admin)
        self.teacher_user = User.objects.create_user(
            email='teacher@school.com',
            password='testpass123',
            is_teacher=True
        )

        # Create programme and class
        self.programme = Programme.objects.create(
            name='General Arts',
            code='ART'
        )
        self.test_class = Class.objects.create(
            level_type=Class.LevelType.SHS,
            level_number=3,
            section='A',
            name='SHS 3A',
            programme=self.programme,
            is_active=True
        )

        # Create another class
        self.test_class_2 = Class.objects.create(
            level_type=Class.LevelType.SHS,
            level_number=2,
            section='A',
            name='SHS 2A',
            programme=self.programme,
            is_active=True
        )

        # Create academic year and term
        self.academic_year = AcademicYear.objects.create(
            name='2024/2025',
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31),
            is_current=True
        )
        self.term = Term.objects.create(
            academic_year=self.academic_year,
            name='First Term',
            term_number=1,
            start_date=date(2024, 9, 1),
            end_date=date(2024, 12, 20),
            is_current=True
        )

        # Create a guardian
        self.guardian = Guardian.objects.create(
            full_name='John Parent',
            phone_number='233241234567'
        )

        # Create active students
        self.active_student_1 = Student.objects.create(
            first_name='Active',
            last_name='Student One',
            admission_number='ACT-001',
            date_of_birth=date(2008, 5, 15),
            gender='M',
            admission_date=date(2024, 9, 1),
            current_class=self.test_class,
            status=Student.Status.ACTIVE
        )
        self.active_student_1.add_guardian(self.guardian, Guardian.Relationship.GUARDIAN, is_primary=True)

        self.active_student_2 = Student.objects.create(
            first_name='Active',
            last_name='Student Two',
            admission_number='ACT-002',
            date_of_birth=date(2008, 6, 20),
            gender='F',
            admission_date=date(2024, 9, 1),
            current_class=self.test_class,
            status=Student.Status.ACTIVE
        )
        self.active_student_2.add_guardian(self.guardian, Guardian.Relationship.GUARDIAN, is_primary=True)

        # Create graduated student (was in test_class)
        self.graduated_student = Student.objects.create(
            first_name='Graduated',
            last_name='Student',
            admission_number='GRAD-001',
            date_of_birth=date(2006, 3, 10),
            gender='M',
            admission_date=date(2021, 9, 1),
            current_class=None,  # Graduated students have no current class
            status=Student.Status.GRADUATED
        )
        self.graduated_student.add_guardian(self.guardian, Guardian.Relationship.GUARDIAN, is_primary=True)

        # Create withdrawn student (was in test_class)
        self.withdrawn_student = Student.objects.create(
            first_name='Withdrawn',
            last_name='Student',
            admission_number='WITH-001',
            date_of_birth=date(2007, 8, 5),
            gender='F',
            admission_date=date(2022, 9, 1),
            current_class=None,
            status=Student.Status.WITHDRAWN
        )
        self.withdrawn_student.add_guardian(self.guardian, Guardian.Relationship.GUARDIAN, is_primary=True)

        # Create enrollments for active students
        Enrollment.objects.create(
            student=self.active_student_1,
            academic_year=self.academic_year,
            class_assigned=self.test_class,
            status=Enrollment.Status.ACTIVE
        )
        Enrollment.objects.create(
            student=self.active_student_2,
            academic_year=self.academic_year,
            class_assigned=self.test_class,
            status=Enrollment.Status.ACTIVE
        )

        # Create enrollment history for graduated student (was in test_class)
        Enrollment.objects.create(
            student=self.graduated_student,
            academic_year=self.academic_year,
            class_assigned=self.test_class,
            status=Enrollment.Status.GRADUATED
        )

        # Create enrollment history for withdrawn student (was in test_class)
        Enrollment.objects.create(
            student=self.withdrawn_student,
            academic_year=self.academic_year,
            class_assigned=self.test_class,
            status=Enrollment.Status.WITHDRAWN
        )


class ReportCardsViewTests(ReportCardsStatusFilterTestCase):
    """Tests for report_cards view basic functionality."""

    def test_report_cards_requires_login(self):
        """Test that report cards page requires authentication."""
        response = self.client.get(reverse('gradebook:reports'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_report_cards_loads_for_admin(self):
        """Test that report cards page loads for admin."""
        self.client.login(email='admin@school.com', password='testpass123')
        response = self.client.get(reverse('gradebook:reports'))
        self.assertEqual(response.status_code, 200)

    def test_admin_sees_status_filter(self):
        """Test that admin sees the status filter dropdown."""
        self.client.login(email='admin@school.com', password='testpass123')
        # Need to select a class to see the full form with status filter
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk}
        )
        self.assertContains(response, 'Student Status')


class ReportCardsStatusFilterTests(ReportCardsStatusFilterTestCase):
    """Tests for status filter functionality."""

    def test_default_status_is_active(self):
        """Test that default status filter is 'active'."""
        self.client.login(email='admin@school.com', password='testpass123')
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk}
        )
        self.assertEqual(response.status_code, 200)
        # Should show active students only (template shows "Last, First" format)
        self.assertContains(response, 'Student One, Active')
        self.assertContains(response, 'Student Two, Active')
        # Should not show graduated/withdrawn students
        self.assertNotContains(response, 'Student, Graduated')
        self.assertNotContains(response, 'Student, Withdrawn')

    def test_filter_by_active_status(self):
        """Test filtering by active status explicitly."""
        self.client.login(email='admin@school.com', password='testpass123')
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk, 'status': 'active'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student One, Active')
        self.assertContains(response, 'Student Two, Active')
        self.assertNotContains(response, 'Student, Graduated')

    def test_filter_by_graduated_status(self):
        """Test filtering by graduated status shows graduated students."""
        self.client.login(email='admin@school.com', password='testpass123')
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk, 'status': 'graduated'}
        )
        self.assertEqual(response.status_code, 200)
        # Should show graduated student who was enrolled in this class
        self.assertContains(response, 'Student, Graduated')
        # Should not show active or withdrawn students
        self.assertNotContains(response, 'Student One, Active')
        self.assertNotContains(response, 'Student, Withdrawn')

    def test_filter_by_withdrawn_status(self):
        """Test filtering by withdrawn status shows withdrawn students."""
        self.client.login(email='admin@school.com', password='testpass123')
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk, 'status': 'withdrawn'}
        )
        self.assertEqual(response.status_code, 200)
        # Should show withdrawn student who was enrolled in this class
        self.assertContains(response, 'Student, Withdrawn')
        # Should not show active or graduated students
        self.assertNotContains(response, 'Student One, Active')
        self.assertNotContains(response, 'Student, Graduated')

    def test_non_active_filter_uses_enrollment_history(self):
        """Test that non-active status filter uses enrollment history."""
        self.client.login(email='admin@school.com', password='testpass123')

        # Graduated student was enrolled in test_class, not test_class_2
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class_2.pk, 'status': 'graduated'}
        )
        self.assertEqual(response.status_code, 200)
        # Should not show graduated student (was not in test_class_2)
        self.assertNotContains(response, 'Student, Graduated')

    def test_empty_result_for_status_without_students(self):
        """Test empty result when no students match the status filter."""
        self.client.login(email='admin@school.com', password='testpass123')
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk, 'status': 'suspended'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No suspended students found for this class')

    def test_info_alert_shown_for_non_active_status(self):
        """Test info alert is shown when filtering by non-active status."""
        self.client.login(email='admin@school.com', password='testpass123')
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk, 'status': 'graduated'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Viewing')
        self.assertContains(response, 'Graduated')
        self.assertContains(response, 'students who were enrolled in')

    def test_action_buttons_hidden_for_non_active_status(self):
        """Test action buttons are hidden for non-active status."""
        self.client.login(email='admin@school.com', password='testpass123')

        # For active status, should see action buttons
        # Note: Button text uses responsive spans, so we check for the visible text
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk, 'status': 'active'}
        )
        self.assertContains(response, 'Remarks')  # Part of "Enter Remarks" button
        self.assertContains(response, 'remarks/bulk')  # URL for remarks button
        self.assertContains(response, 'distribute')  # URL for distribute button

        # For graduated status, should not see action buttons
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk, 'status': 'graduated'}
        )
        self.assertNotContains(response, 'remarks/bulk')  # URL for remarks button
        self.assertNotContains(response, 'reports/distribute')  # URL for distribute button

    def test_student_count_badge_correct(self):
        """Test that student count badge shows correct count."""
        self.client.login(email='admin@school.com', password='testpass123')

        # Active status: 2 students
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk, 'status': 'active'}
        )
        self.assertContains(response, '2 students')

        # Graduated status: 1 student
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk, 'status': 'graduated'}
        )
        self.assertContains(response, '1 students')

    def test_transcript_link_available_for_all_statuses(self):
        """Test transcript link is available for students of all statuses."""
        self.client.login(email='admin@school.com', password='testpass123')

        # Check transcript link for graduated student
        response = self.client.get(
            reverse('gradebook:reports'),
            {'class': self.test_class.pk, 'status': 'graduated'}
        )
        self.assertContains(response, f"transcript/{self.graduated_student.pk}")


class SubjectTermGradeCalculationTest(GradebookTenantTestCase):
    """Tests for the calculate_scores method of the SubjectTermGrade model."""

    def setUp(self):
        super().setUp()
        self.academic_year = AcademicYear.objects.create(name='2024/2025', start_date=date(2024, 9, 1), end_date=date(2025, 7, 31), is_current=True)
        self.term = Term.objects.create(academic_year=self.academic_year, name='First Term', term_number=1, start_date=date(2024, 9, 1), end_date=date(2024, 12, 20), is_current=True)
        self.student = Student.objects.create(first_name='Test', last_name='Student', admission_number='TEST-001', status='active', date_of_birth=date(2010, 1, 1), admission_date=date(2020, 9, 1))
        self.subject = Subject.objects.create(name='Mathematics', short_name='Math')

        # Assessment categories
        self.class_score_cat = AssessmentCategory.objects.create(name='Class Score', short_name='CA', category_type='CLASS_SCORE', percentage=30)
        self.exam_cat = AssessmentCategory.objects.create(name='Examination', short_name='EXAM', category_type='EXAM', percentage=70)

        # Assignments
        self.assignment1 = Assignment.objects.create(assessment_category=self.class_score_cat, subject=self.subject, term=self.term, name='Quiz 1', points_possible=20, date=date(2024, 9, 15))
        self.assignment2 = Assignment.objects.create(assessment_category=self.class_score_cat, subject=self.subject, term=self.term, name='Homework 1', points_possible=10, date=date(2024, 10, 1))
        self.exam_assignment = Assignment.objects.create(assessment_category=self.exam_cat, subject=self.subject, term=self.term, name='Final Exam', points_possible=100, date=date(2024, 12, 10))

        # Scores
        Score.objects.create(student=self.student, assignment=self.assignment1, points=15)  # 15/20 = 75%
        Score.objects.create(student=self.student, assignment=self.assignment2, points=8)    # 8/10 = 80%
        Score.objects.create(student=self.student, assignment=self.exam_assignment, points=85) # 85/100 = 85%

    def test_calculate_scores(self):
        """Test the calculation of class_score, exam_score, and total_score."""
        subject_grade = SubjectTermGrade(student=self.student, subject=self.subject, term=self.term)
        subject_grade.calculate_scores()

        # CA has two assignments, so each is worth 15% of the final grade (30% / 2)
        # Assignment 1 contribution: (15/20) * 15 = 11.25
        # Assignment 2 contribution: (8/10) * 15 = 12.0
        expected_class_score = Decimal('11.25') + Decimal('12.0') # 23.25

        # Exam has one assignment, so it's worth 70% of the final grade
        # Exam contribution: (85/100) * 70 = 59.5
        expected_exam_score = Decimal('59.5')

        expected_total_score = expected_class_score + expected_exam_score # 82.75

        self.assertAlmostEqual(subject_grade.class_score, expected_class_score, places=2)
        self.assertAlmostEqual(subject_grade.exam_score, expected_exam_score, places=2)
        self.assertAlmostEqual(subject_grade.total_score, expected_total_score, places=2)


# ============ cleanup_unenrolled_grades command ============


class CleanupUnenrolledGradesCommandTests(GradebookTenantTestCase):
    """The command should delete SubjectTermGrade rows for students no longer
    enrolled in a subject, then re-rank class positions — without touching
    grades the student is still enrolled in or classes that don't track
    enrollments."""

    def setUp(self):
        super().setUp()
        self.academic_year = AcademicYear.objects.create(
            name='2024/2025', start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.academic_year, name='First Term', term_number=1,
            start_date=date(2024, 9, 1), end_date=date(2024, 12, 20), is_current=True,
        )
        self.programme = Programme.objects.create(name='General Arts', code='ART')
        self.klass = Class.objects.create(
            level_type='shs', level_number=3, section='A', name='SHS 3A',
            programme=self.programme, is_active=True,
        )
        self.math = Subject.objects.create(name='Mathematics', short_name='MTH')
        self.english = Subject.objects.create(name='English', short_name='ENG')
        self.cs_math = ClassSubject.objects.create(class_assigned=self.klass, subject=self.math)
        self.cs_english = ClassSubject.objects.create(class_assigned=self.klass, subject=self.english)

        self.s1 = Student.objects.create(
            first_name='Ama', last_name='Test', admission_number='STU-001',
            date_of_birth=date(2008, 1, 1), admission_date=date(2024, 9, 1),
            current_class=self.klass, status=Student.Status.ACTIVE,
        )
        self.s2 = Student.objects.create(
            first_name='Kofi', last_name='Test', admission_number='STU-002',
            date_of_birth=date(2008, 1, 1), admission_date=date(2024, 9, 1),
            current_class=self.klass, status=Student.Status.ACTIVE,
        )

        # s1 was unenrolled from Math (inactive); s2 enrolled in both.
        StudentSubjectEnrollment.objects.create(
            student=self.s1, class_subject=self.cs_math, is_active=False
        )
        StudentSubjectEnrollment.objects.create(
            student=self.s1, class_subject=self.cs_english, is_active=True
        )
        StudentSubjectEnrollment.objects.create(
            student=self.s2, class_subject=self.cs_math, is_active=True
        )
        StudentSubjectEnrollment.objects.create(
            student=self.s2, class_subject=self.cs_english, is_active=True
        )

        # Orphaned Math grade for s1 left behind from before the fix.
        self._grade(self.s1, self.math, 80)
        self._grade(self.s1, self.english, 60)
        self._grade(self.s2, self.math, 50)
        self._grade(self.s2, self.english, 90)

        TermReport.objects.create(student=self.s1, term=self.term, out_of=2)
        TermReport.objects.create(student=self.s2, term=self.term, out_of=2)

    def _grade(self, student, subject, score, term=None):
        return SubjectTermGrade.objects.create(
            student=student, subject=subject, term=term or self.term,
            total_score=Decimal(str(score)), is_passing=score >= 50,
        )

    def test_dry_run_changes_nothing(self):
        out = StringIO()
        call_command('cleanup_unenrolled_grades', stdout=out)
        # Orphaned grade still present after a dry run.
        self.assertTrue(
            SubjectTermGrade.objects.filter(
                student=self.s1, subject=self.math, term=self.term
            ).exists()
        )
        self.assertIn('Dry run', out.getvalue())
        self.assertIn('Mathematics', out.getvalue())

    def test_apply_deletes_orphan_only(self):
        call_command('cleanup_unenrolled_grades', apply=True, stdout=StringIO())
        # s1's Math grade (unenrolled) removed...
        self.assertFalse(
            SubjectTermGrade.objects.filter(
                student=self.s1, subject=self.math, term=self.term
            ).exists()
        )
        # ...but everything the students are still enrolled in remains.
        self.assertTrue(SubjectTermGrade.objects.filter(student=self.s1, subject=self.english).exists())
        self.assertTrue(SubjectTermGrade.objects.filter(student=self.s2, subject=self.math).exists())
        self.assertTrue(SubjectTermGrade.objects.filter(student=self.s2, subject=self.english).exists())

    def test_apply_reranks_positions(self):
        call_command('cleanup_unenrolled_grades', apply=True, stdout=StringIO())
        r1 = TermReport.objects.get(student=self.s1, term=self.term)
        r2 = TermReport.objects.get(student=self.s2, term=self.term)
        # s1 now: English 60 -> avg 60; s2: Math 50 + English 90 -> avg 70
        self.assertEqual(r1.average, Decimal('60.00'))
        self.assertEqual(r2.average, Decimal('70.00'))
        self.assertEqual(r2.position, 1)
        self.assertEqual(r1.position, 2)

    def test_skips_class_without_allocations_or_enrollments(self):
        # A class with no subjects allocated and no enrollment tracking is
        # likely misconfigured — leave its grades alone.
        other = Class.objects.create(
            level_type='basic', level_number=4, section='A', name='B4A', is_active=True,
        )
        s3 = Student.objects.create(
            first_name='Yaa', last_name='Test', admission_number='STU-003',
            date_of_birth=date(2012, 1, 1), admission_date=date(2024, 9, 1),
            current_class=other, status=Student.Status.ACTIVE,
        )
        grade = self._grade(s3, self.math, 70)
        call_command('cleanup_unenrolled_grades', apply=True, stdout=StringIO())
        self.assertTrue(SubjectTermGrade.objects.filter(pk=grade.pk).exists())

    def test_detects_unallocated_subject_without_enrollment(self):
        # A class with subjects allocated but NO enrollment tracking: a grade
        # for a subject that isn't allocated (removed from the class) is still
        # detected and removed, while an allocated subject's grade is kept.
        other = Class.objects.create(
            level_type='basic', level_number=4, section='A', name='B4A', is_active=True,
        )
        ClassSubject.objects.create(class_assigned=other, subject=self.english)
        s3 = Student.objects.create(
            first_name='Yaa', last_name='Test', admission_number='STU-003',
            date_of_birth=date(2012, 1, 1), admission_date=date(2024, 9, 1),
            current_class=other, status=Student.Status.ACTIVE,
        )
        TermReport.objects.create(student=s3, term=self.term, out_of=1)
        kept = self._grade(s3, self.english, 70)   # still allocated
        orphan = self._grade(s3, self.math, 80)    # math not allocated to B4A
        call_command('cleanup_unenrolled_grades', apply=True, stdout=StringIO())
        self.assertTrue(SubjectTermGrade.objects.filter(pk=kept.pk).exists())
        self.assertFalse(SubjectTermGrade.objects.filter(pk=orphan.pk).exists())


class TermAttendanceStatsTests(GradebookTenantTestCase):
    """
    Tests for compute_term_attendance_stats (gradebook.utils) - the shared
    day-resolution helper used both by bulk term-report generation
    (_calculate_term_reports) and TermReport.calculate_attendance().

    Term dates are fixed in the past (Sept 2024) so valid-school-day counts
    are deterministic regardless of when the test suite actually runs.
    """

    def setUp(self):
        super().setUp()
        self.academic_year = AcademicYear.objects.create(
            name='2024/2025', start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31), is_current=True,
        )
        # Two full Mon-Fri weeks -> 10 valid school days, no holidays.
        self.term = Term.objects.create(
            academic_year=self.academic_year, name='First Term', term_number=1,
            start_date=date(2024, 9, 2), end_date=date(2024, 9, 13), is_current=True,
        )
        self.klass = Class.objects.create(
            level_type='basic', level_number=1, section='A', name='B1A', is_active=True,
        )
        self.student = Student.objects.create(
            first_name='Ama', last_name='Mensah', admission_number='ATT-001',
            date_of_birth=date(2015, 1, 1), admission_date=date(2024, 9, 1),
            current_class=self.klass, status=Student.Status.ACTIVE,
        )

    def _valid_days(self):
        from core.utils import get_valid_school_days
        return get_valid_school_days(
            self.term.start_date, self.term.end_date, term=self.term
        )

    def test_daily_attendance_present_absent_excused(self):
        valid_days = self._valid_days()
        self.assertEqual(len(valid_days), 10)

        for day, status in zip(valid_days[:3], ['P', 'A', 'E']):
            session = AttendanceSession.objects.create(
                class_assigned=self.klass, date=day,
                session_type=AttendanceSession.SessionType.DAILY,
            )
            AttendanceRecord.objects.create(session=session, student=self.student, status=status)

        stats = compute_term_attendance_stats(self.klass, valid_days, [self.student.id])
        att = stats[self.student.id]
        self.assertEqual(att['days_present'], 1)
        self.assertEqual(att['days_absent'], 1)
        self.assertEqual(att['days_excused'], 1)
        self.assertEqual(att['total_school_days'], 10)

    def test_per_lesson_mixed_status_same_day_counts_once_as_present(self):
        """
        A per-lesson class where the student is Present in one lesson and
        Absent in another on the SAME day must resolve to exactly one
        present day and zero absent days - not double-count the same day
        into both tallies (the bug being fixed here).
        """
        self.klass.attendance_type = Class.AttendanceType.PER_LESSON
        self.klass.save(update_fields=['attendance_type'])

        valid_days = self._valid_days()
        day = valid_days[0]

        subject = Subject.objects.create(name='Mathematics', short_name='MTH', code='MTH')
        class_subject = ClassSubject.objects.create(class_assigned=self.klass, subject=subject)
        period1 = Period.objects.create(name='Period 1', start_time='08:00', end_time='08:40', order=1)
        period2 = Period.objects.create(name='Period 2', start_time='08:40', end_time='09:20', order=2)
        entry1 = TimetableEntry.objects.create(
            class_subject=class_subject, period=period1, weekday=day.isoweekday(),
        )
        entry2 = TimetableEntry.objects.create(
            class_subject=class_subject, period=period2, weekday=day.isoweekday(),
        )

        session1 = AttendanceSession.objects.create(
            class_assigned=self.klass, date=day, timetable_entry=entry1,
            session_type=AttendanceSession.SessionType.LESSON,
            period=period1, class_subject=class_subject,
        )
        session2 = AttendanceSession.objects.create(
            class_assigned=self.klass, date=day, timetable_entry=entry2,
            session_type=AttendanceSession.SessionType.LESSON,
            period=period2, class_subject=class_subject,
        )
        AttendanceRecord.objects.create(session=session1, student=self.student, status='P')
        AttendanceRecord.objects.create(session=session2, student=self.student, status='A')

        stats = compute_term_attendance_stats(self.klass, valid_days, [self.student.id])
        att = stats[self.student.id]
        self.assertEqual(att['days_present'], 1)
        self.assertEqual(att['days_absent'], 0)

    def test_mid_term_start_shrinks_total_school_days(self):
        """
        A student whose earliest attendance record in this class lands
        partway through the range AND whose admission_date backs up a real
        mid-term transfer (admission after the window started) should have
        total_school_days counted only from that date onward, not the full
        range - otherwise the days before they even joined this class would
        unfairly count against their percentage.
        """
        valid_days = self._valid_days()
        start_index = 3  # 4th valid day
        join_date = valid_days[start_index]

        self.student.admission_date = join_date
        self.student.save(update_fields=['admission_date'])

        session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=join_date,
            session_type=AttendanceSession.SessionType.DAILY,
        )
        AttendanceRecord.objects.create(session=session, student=self.student, status='P')

        stats = compute_term_attendance_stats(self.klass, valid_days, [self.student.id])
        att = stats[self.student.id]
        self.assertEqual(att['total_school_days'], len(valid_days) - start_index)
        self.assertEqual(att['days_present'], 1)

    def test_late_first_record_without_matching_admission_date_does_not_shrink_total_school_days(self):
        """
        The actual bug this guards against: a student enrolled since well
        before the term (admission_date predates it) whose first attendance
        RECORD in this class still lands partway through - e.g. attendance
        tracking itself started late for the whole school, not because this
        student joined late. Without a real transfer to justify it, the
        earliest-record anchor must not apply - total_school_days should be
        the full valid_days range, not shrunk to "days since first tracked".
        """
        valid_days = self._valid_days()
        start_index = 3  # 4th valid day
        first_tracked_date = valid_days[start_index]

        # admission_date already defaults (in setUp) to well before the term.
        session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=first_tracked_date,
            session_type=AttendanceSession.SessionType.DAILY,
        )
        AttendanceRecord.objects.create(session=session, student=self.student, status='P')

        stats = compute_term_attendance_stats(self.klass, valid_days, [self.student.id])
        att = stats[self.student.id]
        self.assertEqual(att['total_school_days'], len(valid_days))
        self.assertEqual(att['days_present'], 1)

    def test_student_with_no_records_is_omitted(self):
        valid_days = self._valid_days()
        stats = compute_term_attendance_stats(self.klass, valid_days, [self.student.id])
        self.assertNotIn(self.student.id, stats)

    def test_wrong_type_session_merges_via_best_status_wins(self):
        """
        A class only ever runs one attendance mode at a time in the UI, but
        attendance_type is a plain mutable field an admin can change after
        sessions already exist (e.g. switching a class from daily to
        per-lesson mid-term) - records aren't filtered by the class's
        CURRENT attendance_type, since doing so would silently erase every
        day recorded under the old mode from every report generated
        afterward (see test_attendance_type_switch_preserves_earlier_history
        below). Instead, a day with sessions of both types resolves through
        the same "best status wins" priority used for same-day per-lesson
        records, regardless of which session_type each one came from - P
        (better) here wins over A even though it comes from a session of a
        different type than the class's current mode, proving this is a
        real merge and not just a filter that happens to agree.
        """
        valid_days = self._valid_days()
        day = valid_days[0]

        daily_session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=day,
            session_type=AttendanceSession.SessionType.DAILY,
        )
        AttendanceRecord.objects.create(session=daily_session, student=self.student, status='A')

        other_type_session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=day,
            session_type=AttendanceSession.SessionType.LESSON,
        )
        AttendanceRecord.objects.create(session=other_type_session, student=self.student, status='P')

        stats = compute_term_attendance_stats(self.klass, valid_days, [self.student.id])
        att = stats[self.student.id]
        self.assertEqual(att['days_present'], 1)
        self.assertEqual(att['days_absent'], 0)

    def test_attendance_type_switch_preserves_earlier_history(self):
        """
        The actual regression this guards against: a class recorded
        attendance under one mode, then got switched to the other mode
        mid-term (a real, supported admin action) - stats generated
        afterward must not lose the earlier days.
        """
        valid_days = self._valid_days()
        daily_day, lesson_day = valid_days[0], valid_days[1]

        daily_session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=daily_day,
            session_type=AttendanceSession.SessionType.DAILY,
        )
        AttendanceRecord.objects.create(session=daily_session, student=self.student, status='P')

        # Admin switches the class to per-lesson attendance after that day.
        self.klass.attendance_type = Class.AttendanceType.PER_LESSON
        self.klass.save(update_fields=['attendance_type'])

        subject = Subject.objects.create(name='Mathematics', short_name='MTH', code='MTH')
        class_subject = ClassSubject.objects.create(class_assigned=self.klass, subject=subject)
        period = Period.objects.create(name='Period 1', start_time='08:00', end_time='08:40', order=1)
        entry = TimetableEntry.objects.create(
            class_subject=class_subject, period=period, weekday=lesson_day.isoweekday(),
        )
        lesson_session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=lesson_day, timetable_entry=entry,
            session_type=AttendanceSession.SessionType.LESSON,
            period=period, class_subject=class_subject,
        )
        AttendanceRecord.objects.create(session=lesson_session, student=self.student, status='P')

        stats = compute_term_attendance_stats(self.klass, valid_days, [self.student.id])
        att = stats[self.student.id]
        # Both the pre-switch DAILY day and the post-switch LESSON day count.
        self.assertEqual(att['days_present'], 2)

    def test_model_method_matches_helper_for_same_student(self):
        """
        TermReport.calculate_attendance() delegates to the same helper - it
        should produce identical numbers to calling the helper directly.
        """
        valid_days = self._valid_days()
        for day, status in zip(valid_days[:4], ['P', 'P', 'A', 'L']):
            session = AttendanceSession.objects.create(
                class_assigned=self.klass, date=day,
                session_type=AttendanceSession.SessionType.DAILY,
            )
            AttendanceRecord.objects.create(session=session, student=self.student, status=status)

        expected = compute_term_attendance_stats(self.klass, valid_days, [self.student.id])[self.student.id]

        report = TermReport.objects.create(student=self.student, term=self.term, out_of=1)
        report.calculate_attendance()

        self.assertEqual(report.days_present, expected['days_present'])
        self.assertEqual(report.days_absent, expected['days_absent'])
        self.assertEqual(report.times_late, expected['times_late'])
        self.assertEqual(report.total_school_days, expected['total_school_days'])
        self.assertEqual(
            report.attendance_percentage,
            round(Decimal(str(expected['days_present'])) / Decimal(str(expected['total_school_days'])) * 100, 2)
        )


class AssignmentCreateLimitTests(GradebookTenantTestCase):
    """
    Tests for the assignment_create view's enforcement of
    AssessmentCategory.max_assessments ("single vs multiple assignments
    per category") and default_max_marks pre-fill - previously
    max_assessments was admin-editable but never actually checked when a
    teacher created an assignment.
    """

    def setUp(self):
        super().setUp()
        self.admin_user = User.objects.create_user(
            email='admin@school.com', password='testpass123', is_school_admin=True,
        )
        self.client.login(email='admin@school.com', password='testpass123')

        self.subject = Subject.objects.create(name='Mathematics', short_name='MTH', code='MTH')
        self.academic_year = AcademicYear.objects.create(
            name='2024/2025', start_date=date(2024, 9, 1), end_date=date(2025, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.academic_year, name='First Term', term_number=1,
            start_date=date(2024, 9, 1), end_date=date(2024, 12, 20), is_current=True,
        )
        self.category = AssessmentCategory.objects.create(
            name='Class Score', short_name='CA', percentage=30, max_assessments=1,
        )

    def _create(self, **overrides):
        data = {
            'subject_id': self.subject.pk,
            'category_id': self.category.pk,
            'date': '2024-09-10',
            'points_possible': '100',
        }
        data.update(overrides)
        return self.client.post(reverse('gradebook:assignment_create'), data)

    def test_first_assignment_in_category_succeeds(self):
        response = self._create()
        self.assertEqual(Assignment.objects.filter(assessment_category=self.category).count(), 1)
        self.assertNotIn(b'already has the maximum', response.content)

    def test_second_assignment_blocked_at_max_assessments_one(self):
        self._create(date='2024-09-10')
        response = self._create(date='2024-09-17')
        self.assertEqual(Assignment.objects.filter(assessment_category=self.category).count(), 1)
        self.assertIn(b'already has the maximum of 1 assignment', response.content)
        # The rejected request must still render something visible (200,
        # not a bare status code with no body a teacher would never see -
        # see the silent-failure pattern this fixes in assignment_create).
        self.assertEqual(response.status_code, 200)

    def test_max_assessments_zero_means_unlimited(self):
        self.category.max_assessments = 0
        self.category.save(update_fields=['max_assessments'])
        self._create(date='2024-09-10')
        self._create(date='2024-09-17')
        self._create(date='2024-09-24')
        self.assertEqual(Assignment.objects.filter(assessment_category=self.category).count(), 3)

    def test_limit_is_scoped_per_subject(self):
        """Hitting the limit for one subject must not block a different
        subject in the same category/term."""
        self._create(date='2024-09-10')
        other_subject = Subject.objects.create(name='English', short_name='ENG', code='ENG')
        response = self._create(subject_id=other_subject.pk, date='2024-09-10')
        self.assertEqual(Assignment.objects.filter(subject=other_subject).count(), 1)
        self.assertNotIn(b'already has the maximum', response.content)

    def test_default_max_marks_used_when_points_left_blank(self):
        self.category.default_max_marks = Decimal('50.00')
        self.category.save(update_fields=['default_max_marks'])
        self._create(points_possible='')
        assignment = Assignment.objects.get(assessment_category=self.category)
        self.assertEqual(assignment.points_possible, Decimal('50.00'))

    def test_explicit_points_possible_overrides_category_default(self):
        self.category.default_max_marks = Decimal('50.00')
        self.category.save(update_fields=['default_max_marks'])
        self._create(points_possible='75')
        assignment = Assignment.objects.get(assessment_category=self.category)
        self.assertEqual(assignment.points_possible, Decimal('75'))

    def test_full_category_shown_disabled_in_dropdown(self):
        self._create(date='2024-09-10')
        response = self.client.get(reverse('gradebook:assignments', args=[self.subject.pk]))
        options = response.context['category_options']
        full_option = next(o for o in options if o['value'] == self.category.pk)
        self.assertIn('Full', full_option['label'])
        self.assertEqual(full_option['attrs'].get('disabled'), 'disabled')

    def test_full_category_option_actually_renders_disabled(self):
        """
        The view context can say `attrs: {'disabled': 'disabled'}` while
        the actual <option> tag still renders without it if the shared
        select_input template's two branches (with/without a `label`) go
        out of sync - checking response.context alone (as the test above
        does) can't catch that; this checks the real HTML output.
        """
        self._create(date='2024-09-10')
        response = self.client.get(reverse('gradebook:assignments', args=[self.subject.pk]))
        content = response.content.decode()
        option_html = content[content.index(f'value="{self.category.pk}"'):]
        option_html = option_html[:option_html.index('</option>')]
        self.assertIn('disabled="disabled"', option_html)

    def test_default_max_marks_rendered_as_option_data_attribute(self):
        self.category.default_max_marks = Decimal('50.00')
        self.category.save(update_fields=['default_max_marks'])
        response = self.client.get(reverse('gradebook:assignments', args=[self.subject.pk]))
        content = response.content.decode()
        option_html = content[content.index(f'value="{self.category.pk}"'):]
        option_html = option_html[:option_html.index('</option>')]
        self.assertIn('data-default-marks="50.00"', option_html)

    def test_editing_assignment_into_full_category_is_blocked(self):
        """
        assignment_create enforces max_assessments, but assignment_edit
        lets an admin move an existing assignment into a different category
        by changing category_id - that reassignment must be checked too,
        or the cap could be bypassed entirely by editing around it.
        """
        self._create(date='2024-09-10')  # fills self.category (max_assessments=1)

        other_category = AssessmentCategory.objects.create(
            name='Exam', short_name='EXM', percentage=20, max_assessments=1,
        )
        other_assignment = Assignment.objects.create(
            assessment_category=other_category, subject=self.subject, term=self.term,
            name='EXM (Sep 17)', points_possible=100, date=date(2024, 9, 17),
        )

        response = self.client.post(
            reverse('gradebook:assignment_edit', args=[other_assignment.pk]),
            {'name': other_assignment.name, 'category_id': self.category.pk},
        )
        self.assertEqual(response.status_code, 400)
        other_assignment.refresh_from_db()
        self.assertEqual(other_assignment.assessment_category, other_category)
        self.assertEqual(Assignment.objects.filter(assessment_category=self.category).count(), 1)

    def test_editing_assignment_into_category_with_room_succeeds(self):
        other_category = AssessmentCategory.objects.create(
            name='Exam', short_name='EXM', percentage=20, max_assessments=1,
        )
        assignment = Assignment.objects.create(
            assessment_category=other_category, subject=self.subject, term=self.term,
            name='EXM (Sep 17)', points_possible=100, date=date(2024, 9, 17),
        )
        empty_category = AssessmentCategory.objects.create(
            name='Project', short_name='PRJ', percentage=10, max_assessments=1,
        )

        response = self.client.post(
            reverse('gradebook:assignment_edit', args=[assignment.pk]),
            {'name': assignment.name, 'category_id': empty_category.pk},
        )
        self.assertEqual(response.status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.assessment_category, empty_category)


class CategoryMaxAssessmentsDefaultTests(GradebookTenantTestCase):
    """
    category_create/category_edit parse max_assessments via
    `_safe_int(request.POST.get('max_assessments', 1))` - the `1` there is
    dict.get's fallback for a MISSING key, not _safe_int's own default, so
    it never actually applied when the form field was present but blank;
    _safe_int would silently fall back to its own default of 0 ('no
    maximum') instead, defeating the one-assignment-per-category default.
    """

    def setUp(self):
        super().setUp()
        self.admin_user = User.objects.create_user(
            email='admin@school.com', password='testpass123', is_school_admin=True,
        )
        self.client.login(email='admin@school.com', password='testpass123')

    def test_create_with_blank_max_assessments_defaults_to_one(self):
        response = self.client.post(reverse('gradebook:category_create'), {
            'name': 'Class Score', 'short_name': 'CA', 'percentage': '30',
            'max_assessments': '',
        })
        self.assertEqual(response.status_code, 204)
        category = AssessmentCategory.objects.get(short_name='CA')
        self.assertEqual(category.max_assessments, 1)

    def test_edit_with_blank_max_assessments_defaults_to_one(self):
        category = AssessmentCategory.objects.create(
            name='Class Score', short_name='CA', percentage=30, max_assessments=5,
        )
        response = self.client.post(reverse('gradebook:category_edit', args=[category.pk]), {
            'name': 'Class Score', 'short_name': 'CA', 'percentage': '30',
            'max_assessments': '', 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 204)
        category.refresh_from_db()
        self.assertEqual(category.max_assessments, 1)


class RemarkTemplateModalRendersTests(GradebookTenantTestCase):
    """
    modal_remark_template.html reads `template.category|default:form_data.category`
    (and the same pattern for content/order) - Django resolves a filter's
    argument (the part after `default:`) without the silent-failure handling
    it gives the primary variable, so if `form_data` is missing from the
    context entirely, resolving `form_data.category` raises VariableDoesNotExist
    and 500s instead of just falling through. Every render path below has to
    supply `form_data` (with the actual keys, not just an empty dict - an
    empty dict still fails the same way once `.category` is looked up on it).
    """

    def setUp(self):
        super().setUp()
        self.admin_user = User.objects.create_user(
            email='admin@school.com',
            password='testpass123',
            is_school_admin=True
        )
        self.client.login(email='admin@school.com', password='testpass123')
        self.template = RemarkTemplate.objects.create(
            category='GOOD',
            content='{student_name} performed well.',
            order=1,
        )

    def test_create_get_renders(self):
        response = self.client.get(reverse('gradebook:remark_template_create'))
        self.assertEqual(response.status_code, 200)

    def test_create_post_with_empty_content_rerenders(self):
        response = self.client.post(reverse('gradebook:remark_template_create'), {
            'category': 'GENERAL', 'content': '', 'order': '0',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Remark content is required', response.content)

    def test_edit_get_renders(self):
        response = self.client.get(
            reverse('gradebook:remark_template_edit', args=[self.template.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_edit_post_with_empty_content_rerenders(self):
        response = self.client.post(
            reverse('gradebook:remark_template_edit', args=[self.template.pk]),
            {'category': 'AVERAGE', 'content': '', 'order': '2'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Remark content is required', response.content)


class HeadTeacherMessageOnReportCardTests(ReportCardsStatusFilterTestCase):
    """
    Term.head_teacher_message is a single admin-authored note meant to
    appear on every report card generated for that term (e.g. a reopening
    date) - unlike TermReport.head_teacher_remark, which is per-student.
    Since current_term is already threaded into every report-card render
    path, setting the field should be immediately visible everywhere
    without any per-student wiring.
    """

    def setUp(self):
        super().setUp()
        cache.clear()  # Term.get_current() caches per-tenant for 1h
        self.addCleanup(cache.clear)
        self.client.login(email='admin@school.com', password='testpass123')
        TermReport.objects.create(student=self.active_student_1, term=self.term)

    def test_message_shown_on_web_report_card_when_set(self):
        self.term.head_teacher_message = 'School reopens Monday, January 12th.'
        self.term.save(update_fields=['head_teacher_message'])

        response = self.client.get(reverse('gradebook:student_report', args=[self.active_student_1.pk]))
        self.assertContains(response, 'School reopens Monday, January 12th.')

    def test_message_box_omitted_when_blank(self):
        response = self.client.get(reverse('gradebook:student_report', args=[self.active_student_1.pk]))
        self.assertNotContains(response, "Head Teacher's Message")

    def test_message_shown_on_print_report_card(self):
        self.term.head_teacher_message = 'Congratulations on a great term!'
        self.term.save(update_fields=['head_teacher_message'])

        response = self.client.get(reverse('gradebook:report_card_print', args=[self.active_student_1.pk]))
        self.assertContains(response, 'Congratulations on a great term!')

    def test_message_visible_for_a_student_with_no_term_report_yet(self):
        """The message is a Term-level field, not tied to a computed
        TermReport - it should still show even before grades are entered."""
        self.term.head_teacher_message = 'Reminder: fees due by end of week.'
        self.term.save(update_fields=['head_teacher_message'])

        response = self.client.get(reverse('gradebook:student_report', args=[self.active_student_2.pk]))
        self.assertContains(response, 'Reminder: fees due by end of week.')

    def test_pdf_download_still_succeeds_with_message_set(self):
        self.term.head_teacher_message = 'See you next term!'
        self.term.save(update_fields=['head_teacher_message'])

        response = self.client.get(reverse('gradebook:download_report_pdf', args=[self.active_student_1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get('Content-Type'), 'application/pdf')
