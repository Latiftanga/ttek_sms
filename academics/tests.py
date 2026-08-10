"""
Tests for the academics app.

Focuses on:
- Subject enrollment logic (SHS vs non-SHS)
- Student enrollment with auto subject assignment
- Class promotion with subject transfer
- Subject sync utility
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from academics.models import (
    Class, Subject, ClassSubject, StudentSubjectEnrollment, Programme,
    AttendanceSession, AttendanceRecord, Period, TimetableEntry,
)
from students.models import Student, Guardian, Enrollment
from teachers.models import Teacher
from core.models import AcademicYear, Term, SchoolSettings, SchoolHoliday
from gradebook.models import (
    Assignment, AssessmentCategory, Score, SubjectTermGrade, TermReport
)

User = get_user_model()


# =============================================================================
# BASE TEST CASE
# =============================================================================

class AcademicsTestCase(TenantTestCase):
    """Base test case with common setup for academics tests."""

    @classmethod
    def setup_tenant(cls, tenant):
        """Called when tenant is created."""
        tenant.name = 'Test School'
        tenant.short_name = 'TEST'

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.client = TenantClient(self.tenant)

        # Create admin user
        self.admin_user = User.objects.create_user(
            email='admin@school.com',
            password='testpass123',
            is_school_admin=True
        )
        self.client.login(email='admin@school.com', password='testpass123')

        # Create academic year
        self.current_year = AcademicYear.objects.create(
            name='2024/2025',
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31),
            is_current=True
        )
        self.next_year = AcademicYear.objects.create(
            name='2025/2026',
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_current=False
        )

        # Create programme for SHS
        self.programme = Programme.objects.create(
            name='General Arts',
            code='ART',
            required_electives=4
        )

        # Create guardian
        self.guardian = Guardian.objects.create(
            full_name='Test Guardian',
            phone_number='0201234567'
        )

        # Create teacher
        self.teacher = Teacher.objects.create(
            first_name='John',
            last_name='Teacher',
            email='teacher@school.com',
            phone_number='0201234568',
            date_of_birth=date(1985, 5, 15),
            employment_date=date(2020, 1, 1)
        )

    def create_class(self, level_type, level_number, section='A', programme=None):
        """Helper to create a class."""
        name = f"{level_type[0]}{level_number}-{section}"
        if programme:
            name = f"{level_number}{programme.code}-{section}"
        return Class.objects.create(
            level_type=level_type,
            level_number=level_number,
            section=section,
            name=name,
            programme=programme,
            is_active=True
        )

    def create_subject(self, name, code, is_core=True):
        """Helper to create a subject."""
        return Subject.objects.create(
            name=name,
            code=code,
            short_name=code,  # Use code as short_name to ensure uniqueness
            is_core=is_core
        )

    def create_class_subject(self, class_obj, subject, teacher=None):
        """Helper to create a class subject assignment."""
        return ClassSubject.objects.create(
            class_assigned=class_obj,
            subject=subject,
            teacher=teacher or self.teacher
        )

    def create_student(self, first_name, admission_number, class_obj=None):
        """Helper to create a student."""
        student = Student.objects.create(
            first_name=first_name,
            last_name='Test',
            date_of_birth=date(2010, 1, 1),
            gender='M',
            admission_number=admission_number,
            admission_date=date(2024, 1, 1),
            current_class=class_obj,
            status=Student.Status.ACTIVE
        )
        student.add_guardian(self.guardian, Guardian.Relationship.GUARDIAN, is_primary=True)
        return student

    def create_enrollment(self, student, class_obj):
        """Helper to create an enrollment."""
        return Enrollment.objects.create(
            student=student,
            academic_year=self.current_year,
            class_assigned=class_obj,
            status=Enrollment.Status.ACTIVE
        )


# =============================================================================
# MODEL TESTS: StudentSubjectEnrollment
# =============================================================================

class StudentSubjectEnrollmentModelTests(AcademicsTestCase):
    """Tests for StudentSubjectEnrollment model methods."""

    def test_enroll_student_in_class_subjects_basic_school_all_subjects(self):
        """Test that Basic school students get enrolled in ALL subjects."""
        # Create Basic class
        basic_class = self.create_class(Class.LevelType.BASIC, 1)

        # Create subjects (mix of core and elective - but for Basic, all should be enrolled)
        math = self.create_subject('Mathematics', 'MATH', is_core=True)
        english = self.create_subject('English', 'ENG', is_core=True)
        french = self.create_subject('French', 'FRE', is_core=False)  # Elective
        music = self.create_subject('Music', 'MUS', is_core=False)  # Elective

        # Assign all subjects to class
        self.create_class_subject(basic_class, math)
        self.create_class_subject(basic_class, english)
        self.create_class_subject(basic_class, french)
        self.create_class_subject(basic_class, music)

        # Create student
        student = self.create_student('John', 'STU-001')

        # Enroll student in class subjects
        enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, basic_class
        )

        # Should be enrolled in ALL 4 subjects (core + electives)
        self.assertEqual(len(enrollments), 4)
        self.assertEqual(
            StudentSubjectEnrollment.objects.filter(
                student=student,
                is_active=True
            ).count(),
            4
        )

    def test_enroll_student_in_class_subjects_shs_all_subjects(self):
        """Test that SHS students get enrolled in ALL subjects (simplified - no elective tracking)."""
        # Create SHS class
        shs_class = self.create_class(
            Class.LevelType.SHS, 1, programme=self.programme
        )

        # Create subjects (both core and elective)
        math = self.create_subject('Core Math', 'CMATH', is_core=True)
        english = self.create_subject('Core English', 'CENG', is_core=True)
        french = self.create_subject('French', 'FRE', is_core=False)
        spanish = self.create_subject('Spanish', 'SPA', is_core=False)

        # Assign all subjects to class
        self.create_class_subject(shs_class, math)
        self.create_class_subject(shs_class, english)
        self.create_class_subject(shs_class, french)
        self.create_class_subject(shs_class, spanish)

        # Create student
        student = self.create_student('Jane', 'STU-002')

        # Enroll student in class subjects
        enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, shs_class
        )

        # Should be enrolled in ALL 4 subjects (no distinction between core/elective)
        self.assertEqual(len(enrollments), 4)

        # Verify all subjects are enrolled
        enrolled_subjects = StudentSubjectEnrollment.objects.filter(
            student=student,
            is_active=True
        ).values_list('class_subject__subject__code', flat=True)

        self.assertIn('CMATH', enrolled_subjects)
        self.assertIn('CENG', enrolled_subjects)
        self.assertIn('FRE', enrolled_subjects)
        self.assertIn('SPA', enrolled_subjects)

    def test_enroll_student_in_class_subjects_kg_all_subjects(self):
        """Test that KG students get enrolled in ALL subjects."""
        # Create KG class
        kg_class = self.create_class(Class.LevelType.KG, 1)

        # Create subjects
        numeracy = self.create_subject('Numeracy', 'NUM', is_core=True)
        literacy = self.create_subject('Literacy', 'LIT', is_core=True)
        creative_arts = self.create_subject('Creative Arts', 'ART', is_core=False)

        # Assign subjects to class
        self.create_class_subject(kg_class, numeracy)
        self.create_class_subject(kg_class, literacy)
        self.create_class_subject(kg_class, creative_arts)

        # Create student
        student = self.create_student('Kofi', 'STU-003')

        # Enroll student
        enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, kg_class
        )

        # Should be enrolled in ALL 3 subjects
        self.assertEqual(len(enrollments), 3)

    def test_enroll_student_in_class_subjects_nursery_all_subjects(self):
        """Test that Nursery students get enrolled in ALL subjects."""
        # Create Nursery class
        nursery_class = self.create_class(Class.LevelType.NURSERY, 1)

        # Create subjects
        play = self.create_subject('Play Time', 'PLAY', is_core=True)
        rhymes = self.create_subject('Rhymes', 'RHY', is_core=False)

        # Assign subjects to class
        self.create_class_subject(nursery_class, play)
        self.create_class_subject(nursery_class, rhymes)

        # Create student
        student = self.create_student('Ama', 'STU-004')

        # Enroll student
        enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, nursery_class
        )

        # Should be enrolled in ALL 2 subjects
        self.assertEqual(len(enrollments), 2)

    def test_enroll_student_in_class_subjects_creche_all_subjects(self):
        """Test that Creche students get enrolled in ALL subjects."""
        # Create Creche class
        creche_class = self.create_class(Class.LevelType.CRECHE, 1)

        # Create subjects
        activity = self.create_subject('Activity Time', 'ACT', is_core=True)

        # Assign subjects to class
        self.create_class_subject(creche_class, activity)

        # Create student
        student = self.create_student('Baby', 'STU-005')

        # Enroll student
        enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, creche_class
        )

        # Should be enrolled in the subject
        self.assertEqual(len(enrollments), 1)

    def test_enroll_student_reactivates_previously_deactivated(self):
        """Test that enrollment reactivates previously deactivated enrollments."""
        basic_class = self.create_class(Class.LevelType.BASIC, 2)
        math = self.create_subject('Math', 'MTH', is_core=True)
        class_subject = self.create_class_subject(basic_class, math)

        student = self.create_student('Kwame', 'STU-006')

        # Create an inactive enrollment
        old_enrollment = StudentSubjectEnrollment.objects.create(
            student=student,
            class_subject=class_subject,
            is_active=False
        )

        # Re-enroll student
        enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, basic_class
        )

        # Should reactivate the existing enrollment
        self.assertEqual(len(enrollments), 1)
        old_enrollment.refresh_from_db()
        self.assertTrue(old_enrollment.is_active)

    def test_enroll_student_no_duplicate_active_enrollments(self):
        """Test that no duplicate active enrollments are created."""
        basic_class = self.create_class(Class.LevelType.BASIC, 3)
        science = self.create_subject('Science', 'SCI', is_core=True)
        self.create_class_subject(basic_class, science)

        student = self.create_student('Yaw', 'STU-007')

        # Enroll twice
        first_enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, basic_class
        )
        second_enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, basic_class
        )

        # First should create enrollment, second should not
        self.assertEqual(len(first_enrollments), 1)
        self.assertEqual(len(second_enrollments), 0)

        # Only one active enrollment should exist
        self.assertEqual(
            StudentSubjectEnrollment.objects.filter(
                student=student,
                is_active=True
            ).count(),
            1
        )

    def test_enroll_student_empty_class_no_subjects(self):
        """Test enrolling in a class with no subjects assigned."""
        empty_class = self.create_class(Class.LevelType.BASIC, 4)
        student = self.create_student('Empty', 'STU-008')

        enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, empty_class
        )

        self.assertEqual(len(enrollments), 0)

    def test_enroll_student_shs_with_only_elective_subjects(self):
        """Test SHS class with only elective subjects - all get enrolled."""
        shs_class = self.create_class(
            Class.LevelType.SHS, 2, programme=self.programme
        )

        # Only electives assigned (but still get enrolled - no distinction now)
        elective1 = self.create_subject('Economics', 'ECO', is_core=False)
        elective2 = self.create_subject('Geography', 'GEO', is_core=False)
        self.create_class_subject(shs_class, elective1)
        self.create_class_subject(shs_class, elective2)

        student = self.create_student('ElectiveOnly', 'STU-009')

        enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, shs_class
        )

        # All subjects get enrolled (no core/elective distinction for enrollment)
        self.assertEqual(len(enrollments), 2)


# =============================================================================
# VIEW TESTS: class_student_enroll
# =============================================================================

class ClassStudentEnrollViewTests(AcademicsTestCase):
    """Tests for the class_student_enroll view."""

    def test_enroll_student_auto_enrolls_subjects_basic(self):
        """Test enrolling a student in Basic class auto-enrolls in all subjects."""
        basic_class = self.create_class(Class.LevelType.BASIC, 5)

        # Create and assign subjects
        math = self.create_subject('Math B5', 'MB5', is_core=True)
        art = self.create_subject('Art B5', 'AB5', is_core=False)
        self.create_class_subject(basic_class, math)
        self.create_class_subject(basic_class, art)

        # Create unassigned student
        student = self.create_student('NewStudent', 'STU-010')

        # Enroll via view
        self.client.post(
            reverse('academics:class_student_enroll', args=[basic_class.pk]),
            {'students': [student.pk]}
        )

        # Student should be in class
        student.refresh_from_db()
        self.assertEqual(student.current_class, basic_class)

        # Student should be enrolled in ALL subjects
        subject_enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            is_active=True
        )
        self.assertEqual(subject_enrollments.count(), 2)

    def test_enroll_student_auto_enrolls_subjects_shs(self):
        """Test enrolling a student in SHS class auto-enrolls in ALL subjects."""
        shs_class = self.create_class(
            Class.LevelType.SHS, 1, programme=self.programme
        )

        # Create and assign subjects
        core = self.create_subject('Core Subj', 'COR', is_core=True)
        elective = self.create_subject('Elective Subj', 'ELE', is_core=False)
        self.create_class_subject(shs_class, core)
        self.create_class_subject(shs_class, elective)

        # Create unassigned student
        student = self.create_student('SHSStudent', 'STU-011')

        # Enroll via view
        self.client.post(
            reverse('academics:class_student_enroll', args=[shs_class.pk]),
            {'students': [student.pk]}
        )

        # Student should be enrolled in ALL subjects (no core/elective distinction)
        subject_enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            is_active=True
        )
        self.assertEqual(subject_enrollments.count(), 2)

    def test_enroll_multiple_students(self):
        """Test enrolling multiple students at once."""
        basic_class = self.create_class(Class.LevelType.BASIC, 6)
        math = self.create_subject('Math B6', 'MB6', is_core=True)
        self.create_class_subject(basic_class, math)

        # Create multiple students
        student1 = self.create_student('Student1', 'STU-012')
        student2 = self.create_student('Student2', 'STU-013')
        student3 = self.create_student('Student3', 'STU-014')

        # Enroll all via view
        self.client.post(
            reverse('academics:class_student_enroll', args=[basic_class.pk]),
            {'students': [student1.pk, student2.pk, student3.pk]}
        )

        # All students should be enrolled in subjects
        for student in [student1, student2, student3]:
            student.refresh_from_db()
            self.assertEqual(student.current_class, basic_class)
            self.assertEqual(
                StudentSubjectEnrollment.objects.filter(
                    student=student,
                    is_active=True
                ).count(),
                1
            )



# =============================================================================
# VIEW TESTS: class_promote (now redirects to students:promotion)
# =============================================================================

class ClassPromoteViewTests(AcademicsTestCase):
    """Tests for the class_promote view redirect."""

    def test_class_promote_redirects_to_promotion_page(self):
        """Test that class_promote now redirects to the students promotion page."""
        class_b1 = self.create_class(Class.LevelType.BASIC, 1)
        response = self.client.get(
            reverse('academics:class_promote', args=[class_b1.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/students/promotion/', response.url)

    def test_class_promote_post_redirects(self):
        """Test that POST to class_promote also redirects."""
        class_b1 = self.create_class(Class.LevelType.BASIC, 1)
        response = self.client.post(
            reverse('academics:class_promote', args=[class_b1.pk]),
            {}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/students/promotion/', response.url)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class EnrollmentIntegrationTests(AcademicsTestCase):
    """Integration tests for the complete enrollment workflow."""

    def test_full_student_lifecycle_basic_school(self):
        """Test complete student lifecycle in Basic school using static bucket promotion."""
        from core.models import AcademicYear

        # Create both source and target classes
        b1 = self.create_class(Class.LevelType.BASIC, 1)
        b2 = self.create_class(Class.LevelType.BASIC, 2)

        # Create subjects for B1
        math = self.create_subject('Math B1 Int', 'MB1I', is_core=True)
        english = self.create_subject('English B1 Int', 'EB1I', is_core=False)

        self.create_class_subject(b1, math)
        self.create_class_subject(b1, english)

        # Create subjects for B2 (target needs subjects)
        self.create_class_subject(b2, math)
        self.create_class_subject(b2, english)

        # 1. Create and enroll student in B1
        student = self.create_student('LifecycleStudent', 'STU-024')

        self.client.post(
            reverse('academics:class_student_enroll', args=[b1.pk]),
            {'students': [student.pk]}
        )

        student.refresh_from_db()
        self.assertEqual(student.current_class, b1)

        # Student should have 2 subject enrollments (all subjects for Basic)
        b1_enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            class_subject__class_assigned=b1,
            is_active=True
        )
        self.assertEqual(b1_enrollments.count(), 2)

        # 2. Create enrollment record
        self.create_enrollment(student, b1)

        # 3. Static bucket promote: B1-A students → B2-A
        next_year = AcademicYear.objects.filter(is_current=False).first()
        self.client.post(
            reverse('students:promotion_process'),
            {
                'class_id': str(b1.pk),
                'next_year': str(next_year.pk),
                'target_class_id': str(b2.pk),
                f'action_{student.pk}': 'promote',
            }
        )

        # B1 class is UNCHANGED (static bucket)
        b1.refresh_from_db()
        self.assertEqual(b1.level_number, 1)

        # Old subject enrollments in B1 deactivated
        old_b1_enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            class_subject__class_assigned=b1,
            is_active=True
        )
        self.assertEqual(old_b1_enrollments.count(), 0)

        # New subject enrollments created in B2
        b2_enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            class_subject__class_assigned=b2,
            is_active=True
        )
        self.assertEqual(b2_enrollments.count(), 2)

        # Student moved to B2
        student.refresh_from_db()
        self.assertEqual(student.current_class, b2)

    def test_full_student_lifecycle_shs(self):
        """Test complete SHS student lifecycle - all subjects auto-enrolled."""
        # Create SHS classes
        shs1 = self.create_class(Class.LevelType.SHS, 1, programme=self.programme)

        # Create subjects (both core and elective - all will be enrolled)
        core_math = self.create_subject('Core Math SHS', 'CMS', is_core=True)
        core_eng = self.create_subject('Core English SHS', 'CES', is_core=True)
        elec_french = self.create_subject('French SHS', 'FRS', is_core=False)
        elec_spanish = self.create_subject('Spanish SHS', 'SPS', is_core=False)

        self.create_class_subject(shs1, core_math)
        self.create_class_subject(shs1, core_eng)
        self.create_class_subject(shs1, elec_french)
        self.create_class_subject(shs1, elec_spanish)

        # Enroll student
        student = self.create_student('SHSLifecycle', 'STU-025')

        self.client.post(
            reverse('academics:class_student_enroll', args=[shs1.pk]),
            {'students': [student.pk]}
        )

        # Should have ALL 4 subjects (no manual elective assignment needed)
        enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            is_active=True
        )
        self.assertEqual(enrollments.count(), 4)

        # Verify all subjects are enrolled
        enrolled_codes = list(enrollments.values_list(
            'class_subject__subject__code', flat=True
        ))
        self.assertIn('CMS', enrolled_codes)
        self.assertIn('CES', enrolled_codes)
        self.assertIn('FRS', enrolled_codes)
        self.assertIn('SPS', enrolled_codes)


# =============================================================================
# VIEW TESTS: class_subject_delete cascade cleanup
# =============================================================================

class ClassSubjectDeleteCascadeTests(AcademicsTestCase):
    """Removing a subject from a class should cascade-delete the current term's
    scores and grades for it and re-rank class positions, while leaving past
    terms intact."""

    def setUp(self):
        super().setUp()
        self.term = Term.objects.create(
            academic_year=self.current_year,
            name='First Term', term_number=1,
            start_date=date(2024, 9, 1), end_date=date(2024, 12, 20),
            is_current=True,
        )
        self.klass = self.create_class('shs', 3, programme=self.programme)
        self.math = self.create_subject('Mathematics', 'MTH')
        self.english = self.create_subject('English', 'ENG')
        self.cs_math = self.create_class_subject(self.klass, self.math)
        self.cs_english = self.create_class_subject(self.klass, self.english)

        self.cat = AssessmentCategory.objects.create(
            name='Exam', short_name='EXAM', category_type='EXAM', percentage=100
        )

        self.s1 = self.create_student('Ama', 'STU-001', class_obj=self.klass)
        self.s2 = self.create_student('Kofi', 'STU-002', class_obj=self.klass)

        for student in (self.s1, self.s2):
            for cs in (self.cs_math, self.cs_english):
                StudentSubjectEnrollment.objects.create(
                    student=student, class_subject=cs, is_active=True
                )

        # Grades: both students average 70 initially (tie), so removing Math
        # produces an observable re-rank.
        #   s1: Math 80, English 60  -> after removal English 60
        #   s2: Math 50, English 90  -> after removal English 90 (becomes 1st)
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

    def _score(self, student, subject, term=None):
        assignment, _ = Assignment.objects.get_or_create(
            assessment_category=self.cat, subject=subject, term=term or self.term,
            name='Final', defaults={'points_possible': 100, 'date': date(2024, 12, 1)},
        )
        return Score.objects.create(student=student, assignment=assignment, points=70)

    def _delete_math(self):
        return self.client.post(reverse(
            'academics:class_subject_delete',
            kwargs={'class_pk': self.klass.pk, 'pk': self.cs_math.pk},
        ))

    def test_removes_allocation_and_current_term_grades(self):
        self._delete_math()
        self.assertFalse(
            ClassSubject.objects.filter(pk=self.cs_math.pk).exists()
        )
        # Math grades gone for both students; English grades remain.
        self.assertEqual(
            SubjectTermGrade.objects.filter(subject=self.math, term=self.term).count(), 0
        )
        self.assertEqual(
            SubjectTermGrade.objects.filter(subject=self.english, term=self.term).count(), 2
        )

    def test_deletes_current_term_scores(self):
        self._score(self.s1, self.math)
        self._score(self.s2, self.math)
        self._score(self.s1, self.english)
        self._delete_math()
        self.assertEqual(
            Score.objects.filter(assignment__subject=self.math, assignment__term=self.term).count(), 0
        )
        self.assertEqual(
            Score.objects.filter(assignment__subject=self.english, assignment__term=self.term).count(), 1
        )

    def test_reranks_positions(self):
        self._delete_math()
        r1 = TermReport.objects.get(student=self.s1, term=self.term)
        r2 = TermReport.objects.get(student=self.s2, term=self.term)
        # s2 (English 90) now ranks above s1 (English 60)
        self.assertEqual(r2.position, 1)
        self.assertEqual(r1.position, 2)
        self.assertEqual(r1.out_of, 2)
        self.assertEqual(r2.out_of, 2)
        self.assertEqual(r1.average, Decimal('60.00'))
        self.assertEqual(r2.average, Decimal('90.00'))

    def test_past_term_grades_preserved(self):
        past_year = self.next_year
        past_term = Term.objects.create(
            academic_year=past_year, name='Past Term', term_number=3,
            start_date=date(2025, 9, 1), end_date=date(2025, 12, 20),
            is_current=False,
        )
        past_grade = self._grade(self.s1, self.math, 75, term=past_term)
        self._delete_math()
        self.assertTrue(SubjectTermGrade.objects.filter(pk=past_grade.pk).exists())


# =============================================================================
# ATTENDANCE: PAST-TERM MARKING RESTRICTION / SETTING
# =============================================================================

class AttendanceTermRestrictionTests(AcademicsTestCase):
    """
    Tests for the current-term boundary check on marking/editing attendance,
    and the allow_past_term_attendance school setting that relaxes it for
    dates before the current term (as long as they fall within some
    previously defined term).
    """

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()  # SchoolSettings.load() caches per-tenant for 24h
        self.addCleanup(cache.clear)

        self.klass = self.create_class('basic', 1)
        self.klass.class_teacher = self.teacher
        self.klass.save(update_fields=['class_teacher'])

        self.current_term = Term.objects.create(
            academic_year=self.current_year, name='Term 2', term_number=2,
            start_date=date(2024, 9, 1), end_date=date(2024, 12, 20),
            is_current=True,
        )

        # A genuine past term in an earlier academic year.
        self.past_year = AcademicYear.objects.create(
            name='2023/2024',
            start_date=date(2023, 9, 1),
            end_date=date(2024, 7, 31),
            is_current=False,
        )
        self.past_term = Term.objects.create(
            academic_year=self.past_year, name='Term 2', term_number=2,
            start_date=date(2024, 1, 8), end_date=date(2024, 4, 5),
            is_current=False,
        )

        self.past_date = date(2024, 2, 15)  # Thursday, within self.past_term
        self.no_term_date = date(2023, 8, 1)  # Tuesday, before any defined term

        self.student = self.create_student('Ama', 'STU-001', class_obj=self.klass)

    def _enable_setting(self):
        settings = SchoolSettings.load()
        settings.allow_past_term_attendance = True
        settings.save(update_fields=['allow_past_term_attendance'])

    def test_take_attendance_blocks_past_term_by_default(self):
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.past_date.isoformat(), f'status_{self.student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AttendanceSession.objects.filter(class_assigned=self.klass, date=self.past_date).exists()
        )

    def test_take_attendance_allows_past_term_when_enabled(self):
        self._enable_setting()
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.past_date.isoformat(), f'status_{self.student.pk}': 'A'},
        )
        self.assertEqual(response.status_code, 302)
        session = AttendanceSession.objects.get(class_assigned=self.klass, date=self.past_date)
        record = AttendanceRecord.objects.get(session=session, student=self.student)
        self.assertEqual(record.status, 'A')

    def test_take_attendance_blocks_date_outside_any_term_even_when_enabled(self):
        """Enabling the setting only relaxes the check for a date that falls
        within a real past term - not an arbitrary pre-term date."""
        self._enable_setting()
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.no_term_date.isoformat(), f'status_{self.student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AttendanceSession.objects.filter(class_assigned=self.klass, date=self.no_term_date).exists()
        )

    def test_edit_blocks_past_term_session_by_default(self):
        session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=self.past_date,
            session_type=AttendanceSession.SessionType.DAILY,
        )
        AttendanceRecord.objects.create(session=session, student=self.student, status='P')

        response = self.client.post(
            reverse('academics:class_attendance_edit', args=[self.klass.pk, session.pk]),
            {f'status_{self.student.pk}': 'A'},
        )
        self.assertEqual(response.status_code, 302)
        record = AttendanceRecord.objects.get(session=session, student=self.student)
        self.assertEqual(record.status, 'P')  # unchanged - edit was blocked

    def test_edit_allows_past_term_session_when_enabled(self):
        self._enable_setting()
        session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=self.past_date,
            session_type=AttendanceSession.SessionType.DAILY,
        )
        AttendanceRecord.objects.create(session=session, student=self.student, status='P')

        response = self.client.post(
            reverse('academics:class_attendance_edit', args=[self.klass.pk, session.pk]),
            {f'status_{self.student.pk}': 'A'},
        )
        self.assertEqual(response.status_code, 302)
        record = AttendanceRecord.objects.get(session=session, student=self.student)
        self.assertEqual(record.status, 'A')  # edit went through

    def test_lesson_attendance_blocks_past_term_by_default(self):
        lesson_klass = self.create_class('basic', 2)
        lesson_klass.attendance_type = Class.AttendanceType.PER_LESSON
        lesson_klass.save(update_fields=['attendance_type'])

        period = Period.objects.create(
            name='Period 1', start_time='08:00', end_time='08:40', order=1
        )
        subject = self.create_subject('Mathematics', 'MTH')
        class_subject = self.create_class_subject(lesson_klass, subject)
        entry = TimetableEntry.objects.create(
            class_subject=class_subject, period=period,
            weekday=TimetableEntry.Weekday.THURSDAY,  # matches self.past_date
        )
        student = self.create_student('Kofi', 'STU-002', class_obj=lesson_klass)

        response = self.client.post(
            reverse('academics:take_lesson_attendance', args=[entry.pk]),
            {'date': self.past_date.isoformat(), f'status_{student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AttendanceSession.objects.filter(class_assigned=lesson_klass, date=self.past_date).exists()
        )

    def test_lesson_attendance_allows_past_term_when_enabled(self):
        self._enable_setting()
        lesson_klass = self.create_class('basic', 2)
        lesson_klass.attendance_type = Class.AttendanceType.PER_LESSON
        lesson_klass.save(update_fields=['attendance_type'])

        period = Period.objects.create(
            name='Period 1', start_time='08:00', end_time='08:40', order=1
        )
        subject = self.create_subject('Mathematics', 'MTH')
        class_subject = self.create_class_subject(lesson_klass, subject)
        entry = TimetableEntry.objects.create(
            class_subject=class_subject, period=period,
            weekday=TimetableEntry.Weekday.THURSDAY,
        )
        student = self.create_student('Kofi', 'STU-002', class_obj=lesson_klass)

        response = self.client.post(
            reverse('academics:take_lesson_attendance', args=[entry.pk]),
            {'date': self.past_date.isoformat(), f'status_{student.pk}': 'A'},
        )
        self.assertEqual(response.status_code, 302)
        session = AttendanceSession.objects.get(class_assigned=lesson_klass, date=self.past_date)
        record = AttendanceRecord.objects.get(session=session, student=student)
        self.assertEqual(record.status, 'A')

    def test_future_date_still_blocked_when_setting_enabled(self):
        """The setting only relaxes the past-term boundary, never the
        after-current-term-end one."""
        self._enable_setting()
        future_date = self.current_term.end_date + timedelta(days=5)
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': future_date.isoformat(), f'status_{self.student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AttendanceSession.objects.filter(class_assigned=self.klass, date=future_date).exists()
        )


# =============================================================================
# ATTENDANCE: PER-TERM SCHOOL DAYS OVERRIDE
# =============================================================================

class AttendanceTermSchoolDaysTests(AcademicsTestCase):
    """
    Tests that a term-specific school_days override (Term.school_days) is
    honored by the attendance-marking entry points, taking precedence over
    the school-wide SchoolSettings.school_days default whenever the date
    falls within that term.
    """

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()  # SchoolSettings.load() caches per-tenant for 24h
        self.addCleanup(cache.clear)

        self.klass = self.create_class('basic', 1)
        self.klass.class_teacher = self.teacher
        self.klass.save(update_fields=['class_teacher'])

        # Global default stays Mon-Fri; the term below overrides it.
        self.current_term = Term.objects.create(
            academic_year=self.current_year, name='Term 2', term_number=2,
            start_date=date(2024, 9, 1), end_date=date(2024, 12, 20),
            is_current=True,
        )

        self.friday = date(2024, 9, 6)  # a normal Mon-Fri working day globally
        self.saturday = date(2024, 9, 7)  # a weekend day globally

        self.student = self.create_student('Ama', 'STU-001', class_obj=self.klass)

    def _set_term_school_days(self, csv_value):
        self.current_term.school_days = csv_value
        self.current_term.save(update_fields=['school_days'])

    def test_blocks_a_day_excluded_by_term_override(self):
        """Friday is a normal working day globally, but this term meets
        Mon-Thu only - Friday inside this term should be blocked."""
        self._set_term_school_days('1,2,3,4')  # no Friday
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.friday.isoformat(), f'status_{self.student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AttendanceSession.objects.filter(class_assigned=self.klass, date=self.friday).exists()
        )

    def test_allows_a_day_included_by_term_override(self):
        """Saturday isn't a working day globally, but this term adds a
        Saturday session - Saturday inside this term should be allowed."""
        self._set_term_school_days('1,2,3,4,5,6')  # adds Saturday
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.saturday.isoformat(), f'status_{self.student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AttendanceSession.objects.filter(class_assigned=self.klass, date=self.saturday).exists()
        )

    def test_blank_term_school_days_falls_back_to_global(self):
        """No override set - Saturday inside this term is still blocked,
        matching the school-wide default."""
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.saturday.isoformat(), f'status_{self.student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AttendanceSession.objects.filter(class_assigned=self.klass, date=self.saturday).exists()
        )

    def test_take_attendance_dashboard_entry_point_honors_override(self):
        """The teacher-dashboard equivalent (core:take_attendance) applies
        the same term-specific override."""
        self._set_term_school_days('1,2,3,4,5,6')  # adds Saturday
        response = self.client.post(
            reverse('core:take_attendance', args=[self.klass.pk]),
            {'date': self.saturday.isoformat(), f'status_{self.student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AttendanceSession.objects.filter(class_assigned=self.klass, date=self.saturday).exists()
        )

    def test_lesson_attendance_honors_term_override(self):
        """Per-lesson attendance (take_lesson_attendance) also honors a
        term-specific school_days override."""
        self._set_term_school_days('1,2,3,4')  # no Friday

        lesson_klass = self.create_class('basic', 2)
        lesson_klass.attendance_type = Class.AttendanceType.PER_LESSON
        lesson_klass.save(update_fields=['attendance_type'])

        period = Period.objects.create(
            name='Period 1', start_time='08:00', end_time='08:40', order=1
        )
        subject = self.create_subject('Mathematics', 'MTH')
        class_subject = self.create_class_subject(lesson_klass, subject)
        entry = TimetableEntry.objects.create(
            class_subject=class_subject, period=period,
            weekday=TimetableEntry.Weekday.FRIDAY,
        )
        student = self.create_student('Kofi', 'STU-002', class_obj=lesson_klass)

        response = self.client.post(
            reverse('academics:take_lesson_attendance', args=[entry.pk]),
            {'date': self.friday.isoformat(), f'status_{student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AttendanceSession.objects.filter(class_assigned=lesson_klass, date=self.friday).exists()
        )


# =============================================================================
# ATTENDANCE: CATCHING UP ON A LAPSED TERM
# =============================================================================

class AttendanceTermEndedCatchUpTests(AcademicsTestCase):
    """
    If the current term's end date has already passed (a teacher fell
    behind and the term rolled over before they finished marking), landing
    on a class with no explicit date should offer the most recent valid day
    *within* the term instead of a dead block - the teacher can still catch
    up on unmarked past days, bounded by the term's own start/end dates.
    """

    def setUp(self):
        super().setUp()
        cache.clear()  # Term.get_current() caches per-tenant for 1h
        self.addCleanup(cache.clear)

        today = timezone.localdate()
        self.lapsed_year = AcademicYear.objects.create(
            name='Lapsed Year',
            start_date=today - timedelta(days=60),
            end_date=today + timedelta(days=60),
            is_current=False,
        )
        self.lapsed_term = Term.objects.create(
            academic_year=self.lapsed_year, name='Lapsed Term', term_number=1,
            start_date=today - timedelta(days=20),
            end_date=today - timedelta(days=5),
            is_current=True,
        )
        self.klass = self.create_class('basic', 1)
        self.klass.class_teacher = self.teacher
        self.klass.save(update_fields=['class_teacher'])
        self.student = self.create_student('Ama', 'STU-100', class_obj=self.klass)

    def test_class_attendance_take_lands_within_lapsed_term_instead_of_blocking(self):
        response = self.client.get(
            reverse('academics:class_attendance_take', args=[self.klass.pk])
        )
        self.assertEqual(response.status_code, 200)
        session = AttendanceSession.objects.filter(class_assigned=self.klass).first()
        self.assertIsNotNone(session, 'Expected a session to be opened within the lapsed term')
        self.assertGreaterEqual(session.date, self.lapsed_term.start_date)
        self.assertLessEqual(session.date, self.lapsed_term.end_date)

    def test_take_attendance_dashboard_entry_point_lands_within_lapsed_term(self):
        response = self.client.get(
            reverse('core:take_attendance', args=[self.klass.pk])
        )
        self.assertEqual(response.status_code, 200)
        session = AttendanceSession.objects.filter(class_assigned=self.klass).first()
        self.assertIsNotNone(session, 'Expected a session to be opened within the lapsed term')
        self.assertGreaterEqual(session.date, self.lapsed_term.start_date)
        self.assertLessEqual(session.date, self.lapsed_term.end_date)

    def test_explicit_date_beyond_lapsed_term_end_is_still_blocked(self):
        """The auto-landing relaxation only applies when no date was
        explicitly chosen - an explicit pick outside the term is still
        rejected, same as before."""
        beyond_end = self.lapsed_term.end_date + timedelta(days=1)
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': beyond_end.isoformat(), f'status_{self.student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AttendanceSession.objects.filter(class_assigned=self.klass, date=beyond_end).exists()
        )

    def test_take_lesson_attendance_lands_on_matching_weekday_within_lapsed_term(self):
        """Per-lesson attendance is tied to a fixed weekday slot, so the
        catch-up landing must preserve entry.weekday rather than walking
        back day by day like the daily flow does."""
        lesson_klass = self.create_class('basic', 2)
        lesson_klass.attendance_type = Class.AttendanceType.PER_LESSON
        lesson_klass.save(update_fields=['attendance_type'])

        period = Period.objects.create(
            name='Period 1', start_time='08:00', end_time='08:40', order=1
        )
        subject = self.create_subject('Mathematics', 'MTH')
        class_subject = self.create_class_subject(lesson_klass, subject)
        # Monday, not whatever weekday `today` happens to be: the default
        # SchoolSettings.school_days is Mon-Fri, so pinning this to the
        # term's actual end-date weekday made the test flaky whenever that
        # end date landed on a weekend (is_valid_school_day would then
        # reject it downstream). The term's 15-day range guarantees at
        # least one Monday, so this is deterministic regardless of today.
        entry_weekday = 1
        entry = TimetableEntry.objects.create(
            class_subject=class_subject, period=period, weekday=entry_weekday,
        )
        self.create_student('Kofi', 'STU-101', class_obj=lesson_klass)

        response = self.client.get(
            reverse('academics:take_lesson_attendance', args=[entry.pk])
        )
        self.assertEqual(response.status_code, 200)
        session = AttendanceSession.objects.filter(
            class_assigned=lesson_klass, timetable_entry=entry
        ).first()
        self.assertIsNotNone(session, 'Expected a session to be opened within the lapsed term')
        self.assertGreaterEqual(session.date, self.lapsed_term.start_date)
        self.assertLessEqual(session.date, self.lapsed_term.end_date)
        self.assertEqual(session.date.isoweekday(), entry_weekday)

    def test_lesson_attendance_explicit_date_beyond_lapsed_term_end_is_still_blocked(self):
        lesson_klass = self.create_class('basic', 2)
        lesson_klass.attendance_type = Class.AttendanceType.PER_LESSON
        lesson_klass.save(update_fields=['attendance_type'])

        period = Period.objects.create(
            name='Period 1', start_time='08:00', end_time='08:40', order=1
        )
        subject = self.create_subject('Mathematics', 'MTH')
        class_subject = self.create_class_subject(lesson_klass, subject)
        beyond_end = self.lapsed_term.end_date + timedelta(days=1)
        entry = TimetableEntry.objects.create(
            class_subject=class_subject, period=period, weekday=beyond_end.isoweekday(),
        )
        student = self.create_student('Kofi', 'STU-102', class_obj=lesson_klass)

        response = self.client.post(
            reverse('academics:take_lesson_attendance', args=[entry.pk]),
            {'date': beyond_end.isoformat(), f'status_{student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AttendanceSession.objects.filter(class_assigned=lesson_klass, date=beyond_end).exists()
        )

    def test_my_attendance_clamps_today_to_lapsed_term_end(self):
        """
        core:my_attendance's "Today" tab defaulted selected_date straight to
        real today, clamping only if it was too *early* for the current
        term - never if the term had already lapsed and today fell past its
        end date. That unclamped date got baked as an explicit ?date= into
        the "Take Attendance" link (my_attendance_content.html), which
        take_attendance then correctly but silently (toast only) rejected
        for being past term end - looking exactly like a dead Save button.
        lesson_attendance_list already clamped both directions; this closes
        the same gap here.
        """
        teacher_user = User.objects.create_user(
            email='homeroom@school.com', password='testpass123', is_teacher=True,
        )
        self.teacher.user = teacher_user
        self.teacher.save(update_fields=['user'])
        self.client.login(email='homeroom@school.com', password='testpass123')

        response = self.client.get(reverse('core:my_attendance'))
        selected_date = response.context['selected_date']
        # Must land within the lapsed term rather than staying on real
        # "today" (which is after the term ended) - the exact day depends
        # on which weekdays are valid school days, so assert the bounds
        # rather than a specific date.
        self.assertGreaterEqual(selected_date, self.lapsed_term.start_date)
        self.assertLessEqual(selected_date, self.lapsed_term.end_date)

        take_url = reverse('core:take_attendance', args=[self.klass.pk])
        take_response = self.client.get(take_url, {'date': selected_date.isoformat()})
        self.assertEqual(take_response.status_code, 200)

    def test_core_take_attendance_post_saves_for_viewed_date_not_today(self):
        """
        The teacher-portal attendance form's date <input>/dropdown lives
        outside <form id="attendance-form">, and neither it nor the form
        itself carried the viewed date into the POST - so every save
        silently defaulted to request.POST.get('date') being empty,
        target_date falling back to real "today". That went unnoticed
        while "today" usually happened to be a valid date; now that the
        term has lapsed, saving for "today" is correctly rejected,
        making every save silently fail regardless of which date was
        actually being viewed. Posting an explicit past-but-in-term date
        (not today) and asserting the record lands on THAT date, not
        today's, is the exact case that would have caught this.
        """
        teacher_user = User.objects.create_user(
            email='postdate@school.com', password='testpass123', is_teacher=True,
        )
        self.teacher.user = teacher_user
        self.teacher.save(update_fields=['user'])
        self.client.login(email='postdate@school.com', password='testpass123')

        # A guaranteed-valid school day within the lapsed term (not
        # necessarily term.end_date itself, which could land on a weekend).
        my_attendance_response = self.client.get(reverse('core:my_attendance'))
        target_date = my_attendance_response.context['selected_date']
        self.assertNotEqual(target_date, timezone.localdate())

        take_url = reverse('core:take_attendance', args=[self.klass.pk])
        self.client.post(
            take_url,
            {'date': target_date.isoformat(), f'status_{self.student.pk}': 'P'},
        )

        record = AttendanceRecord.objects.get(student=self.student)
        self.assertEqual(record.session.date, target_date)
        self.assertNotEqual(record.session.date, timezone.localdate())


class CoreTakeAttendanceStaysOnPageTests(AcademicsTestCase):
    """
    A successful HTMX save on the teacher-portal "Take Attendance" screen
    used to always close/redirect back to My Attendance (HX-Redirect),
    navigating the teacher away from the date they were just marking. It
    should instead re-render the same date in place, showing the saved
    statuses, so the teacher isn't bounced off the page after every save.
    """

    def setUp(self):
        super().setUp()
        self.klass = self.create_class('basic', 1)
        self.klass.class_teacher = self.teacher
        self.klass.save(update_fields=['class_teacher'])
        self.student = self.create_student('Ama', 'STU-400', class_obj=self.klass)
        # A guaranteed weekday, not necessarily "today" - no Term is set up
        # in this test class, so validity falls back to the default Mon-Fri
        # SchoolSettings.
        today = timezone.localdate()
        self.today = today - timedelta(days=(today.isoweekday() - 1) % 7)

    def test_htmx_save_stays_on_the_same_page_instead_of_redirecting(self):
        response = self.client.post(
            reverse('core:take_attendance', args=[self.klass.pk]),
            {'date': self.today.isoformat(), f'status_{self.student.pk}': 'P'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('HX-Redirect', response)
        self.assertTemplateUsed(response, 'core/teacher/partials/take_attendance_content.html')
        self.assertIn('showToast', response.get('HX-Trigger', ''))
        self.assertIn('success', response.get('HX-Trigger', ''))

        record = AttendanceRecord.objects.get(student=self.student)
        self.assertEqual(record.status, 'P')
        self.assertEqual(record.session.date, self.today)

    def test_non_htmx_save_still_redirects(self):
        response = self.client.post(
            reverse('core:take_attendance', args=[self.klass.pk]),
            {'date': self.today.isoformat(), f'status_{self.student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('core:my_attendance'))


class AcademicsAttendanceStaysOnPageTests(AcademicsTestCase):
    """
    The admin/class-detail attendance-taking flows (class_attendance_take,
    class_attendance_edit, take_lesson_attendance) used to always close and
    HX-Redirect back to the class detail page / lesson list after a
    successful HTMX save, same underlying issue as core:take_attendance.
    This partial is reachable from three different containers - the class
    reports list (#main-content), a class's own Attendance tab
    (#tab-attendance), or the Attendance History modal
    (#modal-edit-content) - so the save must reload into whichever one
    actually triggered it (reflected by the request's HX-Target header),
    not a hardcoded target.
    """

    def setUp(self):
        super().setUp()
        self.klass = self.create_class('basic', 1)
        self.klass.class_teacher = self.teacher
        self.klass.save(update_fields=['class_teacher'])
        self.student = self.create_student('Ama', 'STU-500', class_obj=self.klass)
        today = timezone.localdate()
        self.today = today - timedelta(days=(today.isoweekday() - 1) % 7)

    def test_class_attendance_take_htmx_save_stays_on_page(self):
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.today.isoformat(), f'status_{self.student.pk}': 'P'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('HX-Redirect', response)
        self.assertTemplateUsed(response, 'academics/partials/modal_attendance_take.html')
        self.assertIn('showToast', response.get('HX-Trigger', ''))
        self.assertEqual(
            AttendanceRecord.objects.get(student=self.student, session__date=self.today).status, 'P'
        )

    def test_class_attendance_take_save_reloads_into_the_triggering_tab_target(self):
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.today.isoformat(), f'status_{self.student.pk}': 'P'},
            HTTP_HX_REQUEST='true',
            HTTP_HX_TARGET='tab-attendance',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['reload_target'], '#tab-attendance')
        self.assertTrue(response.context['in_tab'])

    def test_class_attendance_take_save_reloads_into_the_triggering_modal_target(self):
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.today.isoformat(), f'status_{self.student.pk}': 'P'},
            HTTP_HX_REQUEST='true',
            HTTP_HX_TARGET='modal-edit-content',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['reload_target'], '#modal-edit-content')

    def test_class_attendance_take_non_htmx_save_still_redirects(self):
        response = self.client.post(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.today.isoformat(), f'status_{self.student.pk}': 'P'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('tab=attendance', response.url)

    def test_class_attendance_edit_htmx_save_stays_on_page(self):
        session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=self.today,
            session_type=AttendanceSession.SessionType.DAILY,
            created_by=self.teacher,
        )
        AttendanceRecord.objects.create(session=session, student=self.student, status='A')

        response = self.client.post(
            reverse('academics:class_attendance_edit', args=[self.klass.pk, session.pk]),
            {f'status_{self.student.pk}': 'P'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('HX-Redirect', response)
        self.assertTemplateUsed(response, 'academics/partials/modal_attendance_take.html')
        self.assertEqual(AttendanceRecord.objects.get(student=self.student).status, 'P')

    def test_take_lesson_attendance_htmx_save_stays_on_page(self):
        self.klass.attendance_type = Class.AttendanceType.PER_LESSON
        self.klass.save(update_fields=['attendance_type'])

        period = Period.objects.create(
            name='Period 1', start_time='08:00', end_time='08:40', order=1
        )
        subject = self.create_subject('Mathematics', 'MTH')
        class_subject = self.create_class_subject(self.klass, subject)
        entry = TimetableEntry.objects.create(
            class_subject=class_subject, period=period, weekday=self.today.isoweekday(),
        )

        response = self.client.post(
            reverse('academics:take_lesson_attendance', args=[entry.pk]),
            {'date': self.today.isoformat(), f'status_{self.student.pk}': 'P'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('HX-Redirect', response)
        self.assertTemplateUsed(response, 'academics/partials/modal_attendance_take.html')
        self.assertIn('showToast', response.get('HX-Trigger', ''))
        self.assertEqual(
            AttendanceRecord.objects.get(student=self.student, session__timetable_entry=entry).status,
            'P',
        )


class AttendanceDoneStatusReflectsRecordsTests(AcademicsTestCase):
    """
    Opening the "take attendance" screen (a GET request) proactively
    creates an AttendanceSession row so the save endpoint has something to
    attach records to - see class_attendance_take/take_lesson_attendance.
    That alone must not make a class/lesson read as "Done" for admins or
    other teachers; only an actually-saved record should. Sessions are
    created directly here (bypassing the GET view) so these tests don't
    depend on which weekday they happen to run on.
    """

    def setUp(self):
        super().setUp()
        self.klass = self.create_class('basic', 1)
        self.klass.class_teacher = self.teacher
        self.klass.save(update_fields=['class_teacher'])
        self.student = self.create_student('Ama', 'STU-200', class_obj=self.klass)
        self.today = timezone.localdate()

    def _class_summary(self):
        report = self.client.get(reverse('academics:attendance_reports'))
        return report.context['class_summary'], report.context

    def test_empty_session_does_not_mark_class_done(self):
        AttendanceSession.objects.create(
            class_assigned=self.klass, date=self.today,
            session_type=AttendanceSession.SessionType.DAILY,
            created_by=self.teacher,
        )
        summary, ctx = self._class_summary()
        item = next(i for i in summary if i['class'].pk == self.klass.pk)
        self.assertFalse(item['has_today'])
        self.assertEqual(ctx['classes_done_today'], 0)
        self.assertEqual(ctx['classes_pending_today'], 1)

    def test_session_with_a_record_marks_class_done(self):
        session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=self.today,
            session_type=AttendanceSession.SessionType.DAILY,
            created_by=self.teacher,
        )
        AttendanceRecord.objects.create(session=session, student=self.student, status='P')
        summary, ctx = self._class_summary()
        item = next(i for i in summary if i['class'].pk == self.klass.pk)
        self.assertTrue(item['has_today'])
        self.assertEqual(ctx['classes_done_today'], 1)
        self.assertEqual(ctx['classes_pending_today'], 0)

    def test_empty_lesson_session_does_not_mark_lesson_taken(self):
        lesson_klass = self.create_class('basic', 2)
        lesson_klass.attendance_type = Class.AttendanceType.PER_LESSON
        lesson_klass.save(update_fields=['attendance_type'])
        period = Period.objects.create(
            name='Period 1', start_time='08:00', end_time='08:40', order=1
        )
        subject = self.create_subject('Mathematics', 'MTH')
        class_subject = self.create_class_subject(lesson_klass, subject)
        entry = TimetableEntry.objects.create(
            class_subject=class_subject, period=period, weekday=self.today.isoweekday(),
        )
        student = self.create_student('Kofi', 'STU-201', class_obj=lesson_klass)

        AttendanceSession.objects.create(
            class_assigned=lesson_klass, date=self.today, timetable_entry=entry,
            session_type=AttendanceSession.SessionType.LESSON,
            created_by=self.teacher, period=period, class_subject=class_subject,
        )

        response = self.client.get(
            reverse('academics:lesson_attendance_list', args=[lesson_klass.pk])
        )
        lessons = response.context['lessons']
        self.assertEqual(len(lessons), 1)
        self.assertFalse(lessons[0]['attendance_taken'])

        # Now actually save a record for it - it should flip to taken.
        AttendanceRecord.objects.create(
            session=lessons[0]['session'], student=student, status='P'
        )
        response = self.client.get(
            reverse('academics:lesson_attendance_list', args=[lesson_klass.pk])
        )
        self.assertTrue(response.context['lessons'][0]['attendance_taken'])


class AttendanceContextExposesMarkedStatusTests(AcademicsTestCase):
    """
    The "take attendance" GET views must expose whether the selected day's
    session already has real saved records (`attendance_taken`), separately
    from `is_edit` (which only reflects which URL/view was used to get
    here) - the date-picker screen uses this to show a "Marked" vs "Not yet
    marked" badge so a blank, never-touched day can't be mistaken for one
    already saved as all-Present (the default status for an unrecorded
    student is 'P', so the two would otherwise render identically).

    A real current Term is created and dates are pinned to a Monday (rather
    than "today") so these tests don't depend on which weekday they happen
    to run on - same reasoning as AttendanceTermEndedCatchUpTests.
    """

    def setUp(self):
        super().setUp()
        cache.clear()  # Term.get_current() caches per-tenant for 1h
        self.addCleanup(cache.clear)

        today = timezone.localdate()
        self.monday = today - timedelta(days=(today.isoweekday() - 1) % 7)
        # A dedicated year/term anchored to "today" rather than reusing
        # self.current_year (fixed at 2024-09-01..2025-07-31) - this term's
        # bounds need to actually contain self.monday.
        self.year = AcademicYear.objects.create(
            name='Test Year',
            start_date=self.monday - timedelta(days=60),
            end_date=self.monday + timedelta(days=60),
            is_current=False,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name='Test Term', term_number=1,
            start_date=self.monday - timedelta(days=30),
            end_date=self.monday + timedelta(days=30),
            is_current=True,
        )
        self.klass = self.create_class('basic', 1)
        self.klass.class_teacher = self.teacher
        self.klass.save(update_fields=['class_teacher'])
        self.student = self.create_student('Ama', 'STU-500', class_obj=self.klass)

    def test_class_attendance_take_reflects_marked_status(self):
        url = reverse('academics:class_attendance_take', args=[self.klass.pk])
        response = self.client.get(url, {'date': self.monday.isoformat()})
        self.assertFalse(response.context['attendance_taken'])

        session = AttendanceSession.objects.get(
            class_assigned=self.klass, date=self.monday,
            session_type=AttendanceSession.SessionType.DAILY,
        )
        AttendanceRecord.objects.create(session=session, student=self.student, status='P')

        response = self.client.get(url, {'date': self.monday.isoformat()})
        self.assertTrue(response.context['attendance_taken'])

    def test_class_attendance_edit_reflects_marked_status(self):
        session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=self.monday,
            session_type=AttendanceSession.SessionType.DAILY,
            created_by=self.teacher,
        )
        url = reverse('academics:class_attendance_edit', args=[self.klass.pk, session.pk])
        response = self.client.get(url)
        self.assertFalse(response.context['attendance_taken'])

        AttendanceRecord.objects.create(session=session, student=self.student, status='P')
        response = self.client.get(url)
        self.assertTrue(response.context['attendance_taken'])

    def test_take_lesson_attendance_reflects_marked_status(self):
        lesson_klass = self.create_class('basic', 2)
        lesson_klass.attendance_type = Class.AttendanceType.PER_LESSON
        lesson_klass.save(update_fields=['attendance_type'])
        period = Period.objects.create(
            name='Period 1', start_time='08:00', end_time='08:40', order=1
        )
        subject = self.create_subject('Mathematics', 'MTH')
        class_subject = self.create_class_subject(lesson_klass, subject)
        entry = TimetableEntry.objects.create(
            class_subject=class_subject, period=period, weekday=1,
        )
        student = self.create_student('Kofi', 'STU-501', class_obj=lesson_klass)

        url = reverse('academics:take_lesson_attendance', args=[entry.pk])
        response = self.client.get(url, {'date': self.monday.isoformat()})
        self.assertFalse(response.context['attendance_taken'])

        session = AttendanceSession.objects.get(
            class_assigned=lesson_klass, timetable_entry=entry, date=self.monday,
        )
        AttendanceRecord.objects.create(session=session, student=student, status='P')

        response = self.client.get(url, {'date': self.monday.isoformat()})
        self.assertTrue(response.context['attendance_taken'])

    def test_core_take_attendance_reflects_marked_status(self):
        url = reverse('core:take_attendance', args=[self.klass.pk])
        response = self.client.get(url, {'date': self.monday.isoformat()})
        self.assertFalse(response.context['attendance_taken'])

        session = AttendanceSession.objects.get(
            class_assigned=self.klass, date=self.monday,
            session_type=AttendanceSession.SessionType.DAILY,
        )
        AttendanceRecord.objects.create(session=session, student=self.student, status='P')

        response = self.client.get(url, {'date': self.monday.isoformat()})
        self.assertTrue(response.context['attendance_taken'])

    def test_pickable_dates_excludes_weekends_holidays_and_out_of_range(self):
        # A Saturday within the term and safely in the past (so this isolates
        # the weekday rule rather than also being excluded merely for being
        # a future date) - never a valid school day under the default
        # Mon-Fri SchoolSettings, so it must never appear at all.
        saturday = self.monday - timedelta(days=2)
        # A Monday (otherwise valid) explicitly closed as a holiday.
        holiday_monday = self.monday - timedelta(days=7)
        SchoolHoliday.objects.create(name='Staff Day', date=holiday_monday)
        # Before the term even starts.
        before_term = self.term.start_date - timedelta(days=1)
        # Within the term but after "today" - not yet reachable.
        future_monday = self.monday + timedelta(days=7)

        response = self.client.get(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.monday.isoformat()},
        )
        values = {d['value'] for d in response.context['pickable_dates']}
        self.assertNotIn(saturday.isoformat(), values)
        self.assertNotIn(holiday_monday.isoformat(), values)
        self.assertNotIn(before_term.isoformat(), values)
        self.assertNotIn(future_monday.isoformat(), values)
        self.assertIn(self.monday.isoformat(), values)

    def test_pickable_dates_flags_marked_days(self):
        response = self.client.get(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.monday.isoformat()},
        )
        entry = next(
            d for d in response.context['pickable_dates']
            if d['value'] == self.monday.isoformat()
        )
        self.assertFalse(entry['marked'])

        session = AttendanceSession.objects.get(
            class_assigned=self.klass, date=self.monday,
            session_type=AttendanceSession.SessionType.DAILY,
        )
        AttendanceRecord.objects.create(session=session, student=self.student, status='P')

        response = self.client.get(
            reverse('academics:class_attendance_take', args=[self.klass.pk]),
            {'date': self.monday.isoformat()},
        )
        entry = next(
            d for d in response.context['pickable_dates']
            if d['value'] == self.monday.isoformat()
        )
        self.assertTrue(entry['marked'])

    def test_lesson_flow_pickable_dates_flag_marked_days(self):
        lesson_klass = self.create_class('basic', 3)
        lesson_klass.attendance_type = Class.AttendanceType.PER_LESSON
        lesson_klass.save(update_fields=['attendance_type'])
        period = Period.objects.create(
            name='Period 1', start_time='08:00', end_time='08:40', order=1
        )
        subject = self.create_subject('Mathematics', 'MTH')
        class_subject = self.create_class_subject(lesson_klass, subject)
        entry = TimetableEntry.objects.create(
            class_subject=class_subject, period=period, weekday=1,
        )
        student = self.create_student('Kofi', 'STU-502', class_obj=lesson_klass)

        lesson_url = reverse('academics:take_lesson_attendance', args=[entry.pk])
        list_url = reverse('academics:lesson_attendance_list', args=[lesson_klass.pk])

        # Opening the lesson's own take-attendance screen is what creates
        # the (still-empty) session in the first place.
        self.client.get(lesson_url, {'date': self.monday.isoformat()})

        response = self.client.get(list_url, {'date': self.monday.isoformat()})
        entry_dates = {d['value']: d['marked'] for d in response.context['pickable_dates']}
        self.assertFalse(entry_dates[self.monday.isoformat()])

        session = AttendanceSession.objects.get(
            class_assigned=lesson_klass, timetable_entry=entry, date=self.monday,
        )
        AttendanceRecord.objects.create(session=session, student=student, status='P')

        # Both the hub list and the single lesson's own picker should agree.
        response = self.client.get(list_url, {'date': self.monday.isoformat()})
        entry_dates = {d['value']: d['marked'] for d in response.context['pickable_dates']}
        self.assertTrue(entry_dates[self.monday.isoformat()])

        response = self.client.get(lesson_url, {'date': self.monday.isoformat()})
        entry_dates = {d['value']: d['marked'] for d in response.context['pickable_dates']}
        self.assertTrue(entry_dates[self.monday.isoformat()])

    def test_core_take_attendance_pickable_dates_flags_marked_days(self):
        url = reverse('core:take_attendance', args=[self.klass.pk])
        response = self.client.get(url, {'date': self.monday.isoformat()})
        entry = next(
            d for d in response.context['pickable_dates']
            if d['value'] == self.monday.isoformat()
        )
        self.assertFalse(entry['marked'])

        session = AttendanceSession.objects.get(
            class_assigned=self.klass, date=self.monday,
            session_type=AttendanceSession.SessionType.DAILY,
        )
        AttendanceRecord.objects.create(session=session, student=self.student, status='P')

        response = self.client.get(url, {'date': self.monday.isoformat()})
        entry = next(
            d for d in response.context['pickable_dates']
            if d['value'] == self.monday.isoformat()
        )
        self.assertTrue(entry['marked'])


class MyClassesAttendanceButtonVisibilityTests(AcademicsTestCase):
    """
    core:my_classes' Subject Classes cards (classes a teacher teaches a
    subject in but isn't the form master of) should only show "Attend"
    when the class actually lets a non-form-master mark attendance - true
    for per-lesson classes (each subject teacher marks their own lesson)
    but not daily ones (form master/admin only - see
    core.views.take_attendance and
    academics.views.attendance.class_attendance_take's "Daily attendance
    requires the class teacher or admin" check). Showing it unconditionally
    meant a subject teacher on a daily class saw a button that would always
    be rejected if tapped.
    """

    def test_attend_button_shown_only_for_per_lesson_subject_classes(self):
        daily_class = self.create_class('basic', 1)
        per_lesson_class = self.create_class('basic', 2)
        per_lesson_class.attendance_type = Class.AttendanceType.PER_LESSON
        per_lesson_class.save(update_fields=['attendance_type'])

        subject = self.create_subject('Mathematics', 'MTH')
        self.create_class_subject(daily_class, subject, teacher=self.teacher)
        self.create_class_subject(per_lesson_class, subject, teacher=self.teacher)

        teacher_user = User.objects.create_user(
            email='subjectteacher@school.com', password='testpass123', is_teacher=True,
        )
        self.teacher.user = teacher_user
        self.teacher.save(update_fields=['user'])
        self.client.login(email='subjectteacher@school.com', password='testpass123')

        response = self.client.get(reverse('core:my_classes'))
        content = response.content.decode()

        daily_attend_url = reverse('core:take_attendance', args=[daily_class.pk])
        per_lesson_attend_url = reverse('core:take_attendance', args=[per_lesson_class.pk])

        self.assertNotIn(daily_attend_url, content)
        self.assertIn(per_lesson_attend_url, content)


class AttendanceSaveConcurrencyTests(AcademicsTestCase):
    """
    Two overlapping submits for the same session/student (e.g. a double-tap
    on Save under a slow mobile connection) can both see "no existing
    record" and both attempt to insert one, tripping the unique_together
    constraint on the loser. save_attendance_records should resolve that
    as an upsert against the now-current DB state rather than surfacing a
    "failed to save" for a save that actually mostly succeeded.
    """

    def setUp(self):
        super().setUp()
        self.klass = self.create_class('basic', 1)
        self.klass.class_teacher = self.teacher
        self.klass.save(update_fields=['class_teacher'])
        self.student = self.create_student('Ama', 'STU-300', class_obj=self.klass)
        # A guaranteed weekday, not necessarily "today" - no Term is set up
        # in this test class, so validity falls back to the default Mon-Fri
        # SchoolSettings, and real "today" landing on a weekend would make
        # class_attendance_take reject the POST below as not a school day.
        today = timezone.localdate()
        self.today = today - timedelta(days=(today.isoweekday() - 1) % 7)

    def test_concurrent_insert_is_resolved_not_reported_as_failure(self):
        from unittest.mock import patch
        from django.db import IntegrityError

        session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=self.today,
            session_type=AttendanceSession.SessionType.DAILY,
            created_by=self.teacher,
        )

        real_bulk_create = AttendanceRecord.objects.bulk_create
        state = {'calls': 0}

        def flaky_bulk_create(objs, *args, **kwargs):
            state['calls'] += 1
            if state['calls'] == 1:
                # Simulate a concurrent duplicate submission that already
                # landed between this request's SELECT and INSERT.
                AttendanceRecord.objects.create(
                    session=session, student=self.student, status='A'
                )
                raise IntegrityError(
                    'duplicate key value violates unique constraint'
                )
            return real_bulk_create(objs, *args, **kwargs)

        with patch.object(AttendanceRecord.objects, 'bulk_create', side_effect=flaky_bulk_create):
            response = self.client.post(
                reverse('academics:class_attendance_take', args=[self.klass.pk]),
                {'date': self.today.isoformat(), f'status_{self.student.pk}': 'P'},
            )

        # No 500 / "failed to save" - the request should still redirect
        # (success path), and exactly one record should exist, carrying
        # THIS submission's status rather than being left on whatever the
        # "other" concurrent insert set.
        self.assertIn(response.status_code, (302, 204))
        records = AttendanceRecord.objects.filter(session=session, student=self.student)
        self.assertEqual(records.count(), 1)
        self.assertEqual(records.first().status, 'P')


class AttendanceEmptySessionsExcludedFromListsTests(AcademicsTestCase):
    """
    Same root cause as AttendanceDoneStatusReflectsRecordsTests: opening the
    "take attendance" screen creates an AttendanceSession row before anyone
    taps Save. That empty session shouldn't just avoid flipping "Done"
    status - it also shouldn't show up as a blank 0/0 entry in the history
    modal, the Class Detail Attendance tab, or inflate the "sessions" count
    on the per-lesson weekly report.
    """

    def setUp(self):
        super().setUp()
        self.klass = self.create_class('basic', 1)
        self.klass.class_teacher = self.teacher
        self.klass.save(update_fields=['class_teacher'])
        self.student = self.create_student('Ama', 'STU-400', class_obj=self.klass)
        self.today = timezone.localdate()

    def test_empty_session_excluded_from_history_modal(self):
        AttendanceSession.objects.create(
            class_assigned=self.klass, date=self.today,
            session_type=AttendanceSession.SessionType.DAILY,
            created_by=self.teacher,
        )
        response = self.client.get(
            reverse('academics:class_attendance_history', args=[self.klass.pk])
        )
        self.assertEqual(list(response.context['attendance_sessions']), [])

    def test_session_with_a_record_included_in_history_modal(self):
        session = AttendanceSession.objects.create(
            class_assigned=self.klass, date=self.today,
            session_type=AttendanceSession.SessionType.DAILY,
            created_by=self.teacher,
        )
        AttendanceRecord.objects.create(session=session, student=self.student, status='P')
        response = self.client.get(
            reverse('academics:class_attendance_history', args=[self.klass.pk])
        )
        sessions = list(response.context['attendance_sessions'])
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].pk, session.pk)

    def test_empty_session_excluded_from_class_detail_attendance_tab(self):
        AttendanceSession.objects.create(
            class_assigned=self.klass, date=self.today,
            session_type=AttendanceSession.SessionType.DAILY,
            created_by=self.teacher,
        )
        response = self.client.get(reverse('academics:class_detail', args=[self.klass.pk]))
        self.assertEqual(list(response.context['attendance_sessions']), [])

    def test_empty_lesson_session_excluded_from_weekly_report_count(self):
        from academics.utils import get_lesson_attendance_stats

        lesson_klass = self.create_class('basic', 2)
        lesson_klass.attendance_type = Class.AttendanceType.PER_LESSON
        lesson_klass.save(update_fields=['attendance_type'])
        period = Period.objects.create(
            name='Period 1', start_time='08:00', end_time='08:40', order=1
        )
        subject = self.create_subject('Mathematics', 'MTH')
        class_subject = self.create_class_subject(lesson_klass, subject)
        entry = TimetableEntry.objects.create(
            class_subject=class_subject, period=period, weekday=self.today.isoweekday(),
        )
        student = self.create_student('Kofi', 'STU-401', class_obj=lesson_klass)
        other_student = self.create_student('Ama', 'STU-402', class_obj=lesson_klass)

        # An empty session (never saved) plus a real one with one record -
        # "sessions" for this subject should count only the real one, and
        # not be inflated by the join to records fanning out per row.
        AttendanceSession.objects.create(
            class_assigned=lesson_klass, date=self.today, timetable_entry=entry,
            session_type=AttendanceSession.SessionType.LESSON,
            created_by=self.teacher, period=period, class_subject=class_subject,
        )
        taken_session = AttendanceSession.objects.create(
            class_assigned=lesson_klass, date=self.today - timedelta(days=1),
            timetable_entry=entry, session_type=AttendanceSession.SessionType.LESSON,
            created_by=self.teacher, period=period, class_subject=class_subject,
        )
        AttendanceRecord.objects.create(session=taken_session, student=student, status='P')
        AttendanceRecord.objects.create(session=taken_session, student=other_student, status='A')

        stats = get_lesson_attendance_stats(
            lesson_klass, self.today - timedelta(days=7), self.today
        )
        row = next(s for s in stats if s['subject'] == subject)
        self.assertEqual(row['sessions'], 1)
        self.assertEqual(row['present'], 1)
        self.assertEqual(row['absent'], 1)
