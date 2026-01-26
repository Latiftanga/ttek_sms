from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db import models
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from .models import (
    GradingSystem, GradeScale, AssessmentCategory,
    Assignment, Score, SubjectTermGrade
)
from .forms import GradeScaleForm, AssessmentCategoryForm, ScoreForm
from academics.models import Subject, Class, Programme
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
