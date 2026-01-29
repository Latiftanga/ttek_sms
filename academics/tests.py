"""
Tests for the academics app.

Focuses on:
- Subject enrollment logic (SHS vs non-SHS)
- Student enrollment with auto subject assignment
- Class promotion with subject transfer
- Subject sync utility
"""
from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from academics.models import (
    Class, Subject, ClassSubject, StudentSubjectEnrollment, Programme
)
from students.models import Student, Guardian, Enrollment
from teachers.models import Teacher
from core.models import AcademicYear

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

    def test_enroll_student_in_class_subjects_shs_only_core(self):
        """Test that SHS students get enrolled in ONLY core subjects."""
        # Create SHS class
        shs_class = self.create_class(
            Class.LevelType.SHS, 1, programme=self.programme
        )

        # Create subjects
        math = self.create_subject('Core Math', 'CMATH', is_core=True)
        english = self.create_subject('Core English', 'CENG', is_core=True)
        french = self.create_subject('French', 'FRE', is_core=False)  # Elective
        spanish = self.create_subject('Spanish', 'SPA', is_core=False)  # Elective

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

        # Should be enrolled in ONLY 2 core subjects
        self.assertEqual(len(enrollments), 2)

        # Verify only core subjects are enrolled
        enrolled_subjects = StudentSubjectEnrollment.objects.filter(
            student=student,
            is_active=True
        ).values_list('class_subject__subject__code', flat=True)

        self.assertIn('CMATH', enrolled_subjects)
        self.assertIn('CENG', enrolled_subjects)
        self.assertNotIn('FRE', enrolled_subjects)
        self.assertNotIn('SPA', enrolled_subjects)

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

    def test_enroll_student_shs_no_core_subjects(self):
        """Test SHS class with only elective subjects - no auto-enrollment."""
        shs_class = self.create_class(
            Class.LevelType.SHS, 2, programme=self.programme
        )

        # Only electives assigned
        elective1 = self.create_subject('Economics', 'ECO', is_core=False)
        elective2 = self.create_subject('Geography', 'GEO', is_core=False)
        self.create_class_subject(shs_class, elective1)
        self.create_class_subject(shs_class, elective2)

        student = self.create_student('ElectiveOnly', 'STU-009')

        enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, shs_class
        )

        # No enrollments since SHS only auto-enrolls core subjects
        self.assertEqual(len(enrollments), 0)


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
        response = self.client.post(
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
        """Test enrolling a student in SHS class auto-enrolls in core subjects only."""
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

        # Student should be enrolled in ONLY core subject
        subject_enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            is_active=True
        )
        self.assertEqual(subject_enrollments.count(), 1)
        self.assertEqual(
            subject_enrollments.first().class_subject.subject.code,
            'COR'
        )

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
# VIEW TESTS: class_sync_subjects
# =============================================================================

class ClassSyncSubjectsViewTests(AcademicsTestCase):
    """Tests for the class_sync_subjects view."""

    def test_sync_subjects_basic_class(self):
        """Test syncing subjects for Basic class students."""
        basic_class = self.create_class(Class.LevelType.BASIC, 7)

        # Create subjects
        math = self.create_subject('Math B7', 'MB7', is_core=True)
        english = self.create_subject('English B7', 'EB7', is_core=True)
        self.create_class_subject(basic_class, math)
        self.create_class_subject(basic_class, english)

        # Create students already in class but without subject enrollments
        student1 = self.create_student('Sync1', 'STU-015', class_obj=basic_class)
        student2 = self.create_student('Sync2', 'STU-016', class_obj=basic_class)

        # Verify no subject enrollments yet
        self.assertEqual(
            StudentSubjectEnrollment.objects.filter(student=student1).count(),
            0
        )

        # Sync via view
        response = self.client.post(
            reverse('academics:class_sync_subjects', args=[basic_class.pk])
        )

        # Both students should now have subject enrollments
        self.assertEqual(
            StudentSubjectEnrollment.objects.filter(
                student=student1,
                is_active=True
            ).count(),
            2
        )
        self.assertEqual(
            StudentSubjectEnrollment.objects.filter(
                student=student2,
                is_active=True
            ).count(),
            2
        )

    def test_sync_subjects_shs_class(self):
        """Test syncing subjects for SHS class students - core only."""
        shs_class = self.create_class(
            Class.LevelType.SHS, 2, programme=self.programme
        )

        # Create subjects
        core = self.create_subject('SHS Core', 'SC', is_core=True)
        elective = self.create_subject('SHS Elec', 'SE', is_core=False)
        self.create_class_subject(shs_class, core)
        self.create_class_subject(shs_class, elective)

        # Create student in class without subject enrollments
        student = self.create_student('SHSSync', 'STU-017', class_obj=shs_class)

        # Sync via view
        self.client.post(
            reverse('academics:class_sync_subjects', args=[shs_class.pk])
        )

        # Student should only have core subject enrollment
        enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            is_active=True
        )
        self.assertEqual(enrollments.count(), 1)
        self.assertTrue(enrollments.first().class_subject.subject.is_core)

    def test_sync_subjects_get_not_allowed(self):
        """Test that GET request is not allowed."""
        basic_class = self.create_class(Class.LevelType.BASIC, 8)

        response = self.client.get(
            reverse('academics:class_sync_subjects', args=[basic_class.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_sync_subjects_after_adding_new_subject(self):
        """Test sync enrolls students in newly added subject."""
        basic_class = self.create_class(Class.LevelType.BASIC, 9)

        # Create initial subject and student
        math = self.create_subject('Initial Math', 'IM', is_core=True)
        self.create_class_subject(basic_class, math)

        student = self.create_student('InitialStudent', 'STU-018', class_obj=basic_class)

        # Enroll in initial subjects
        StudentSubjectEnrollment.enroll_student_in_class_subjects(student, basic_class)
        self.assertEqual(
            StudentSubjectEnrollment.objects.filter(student=student, is_active=True).count(),
            1
        )

        # Add a new subject to class
        science = self.create_subject('New Science', 'NS', is_core=True)
        self.create_class_subject(basic_class, science)

        # Sync to pick up new subject
        self.client.post(
            reverse('academics:class_sync_subjects', args=[basic_class.pk])
        )

        # Student should now have 2 enrollments
        self.assertEqual(
            StudentSubjectEnrollment.objects.filter(student=student, is_active=True).count(),
            2
        )


# =============================================================================
# VIEW TESTS: class_promote
# =============================================================================

class ClassPromoteViewTests(AcademicsTestCase):
    """Tests for the class_promote view with subject enrollment handling."""

    def test_promote_deactivates_old_subject_enrollments(self):
        """Test that promotion deactivates old class subject enrollments."""
        # Create source and target classes
        class_b1 = self.create_class(Class.LevelType.BASIC, 1)
        class_b2 = self.create_class(Class.LevelType.BASIC, 2)

        # Create subjects for both classes
        math_b1 = self.create_subject('Math B1', 'MTB1', is_core=True)
        math_b2 = self.create_subject('Math B2', 'MTB2', is_core=True)
        self.create_class_subject(class_b1, math_b1)
        self.create_class_subject(class_b2, math_b2)

        # Create student with enrollment
        student = self.create_student('PromoStudent', 'STU-019', class_obj=class_b1)
        self.create_enrollment(student, class_b1)

        # Enroll in B1 subjects
        StudentSubjectEnrollment.enroll_student_in_class_subjects(student, class_b1)
        b1_enrollment = StudentSubjectEnrollment.objects.get(
            student=student,
            class_subject__class_assigned=class_b1
        )
        self.assertTrue(b1_enrollment.is_active)

        # Promote student
        self.client.post(
            reverse('academics:class_promote', args=[class_b1.pk]),
            {
                f'action_{student.pk}': 'promote',
                f'target_class_{student.pk}': str(class_b2.pk),
            }
        )

        # Old subject enrollment should be deactivated
        b1_enrollment.refresh_from_db()
        self.assertFalse(b1_enrollment.is_active)

    def test_promote_creates_new_subject_enrollments(self):
        """Test that promotion creates subject enrollments in new class."""
        # Create source and target classes
        class_b3 = self.create_class(Class.LevelType.BASIC, 3)
        class_b4 = self.create_class(Class.LevelType.BASIC, 4)

        # Create subjects for target class
        math_b4 = self.create_subject('Math B4', 'MTB4', is_core=True)
        english_b4 = self.create_subject('English B4', 'ENB4', is_core=True)
        self.create_class_subject(class_b4, math_b4)
        self.create_class_subject(class_b4, english_b4)

        # Create student with enrollment
        student = self.create_student('PromoStudent2', 'STU-020', class_obj=class_b3)
        self.create_enrollment(student, class_b3)

        # Promote student
        self.client.post(
            reverse('academics:class_promote', args=[class_b3.pk]),
            {
                f'action_{student.pk}': 'promote',
                f'target_class_{student.pk}': str(class_b4.pk),
            }
        )

        # New subject enrollments should exist
        new_enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            class_subject__class_assigned=class_b4,
            is_active=True
        )
        self.assertEqual(new_enrollments.count(), 2)

    def test_promote_shs_only_core_subjects_enrolled(self):
        """Test that SHS promotion only enrolls in core subjects."""
        # Create SHS classes
        shs1 = self.create_class(Class.LevelType.SHS, 1, programme=self.programme)
        shs2 = self.create_class(Class.LevelType.SHS, 2, programme=self.programme)

        # Create subjects for SHS2
        core = self.create_subject('SHS2 Core', 'S2C', is_core=True)
        elective = self.create_subject('SHS2 Elective', 'S2E', is_core=False)
        self.create_class_subject(shs2, core)
        self.create_class_subject(shs2, elective)

        # Create student with enrollment
        student = self.create_student('SHSPromo', 'STU-021', class_obj=shs1)
        self.create_enrollment(student, shs1)

        # Promote student
        self.client.post(
            reverse('academics:class_promote', args=[shs1.pk]),
            {
                f'action_{student.pk}': 'promote',
                f'target_class_{student.pk}': str(shs2.pk),
            }
        )

        # Only core subject should be enrolled
        new_enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            class_subject__class_assigned=shs2,
            is_active=True
        )
        self.assertEqual(new_enrollments.count(), 1)
        self.assertTrue(new_enrollments.first().class_subject.subject.is_core)

    def test_repeat_keeps_same_class_subjects(self):
        """Test that repeating a student doesn't change subject enrollments."""
        # Create class with subjects
        basic_class = self.create_class(Class.LevelType.BASIC, 5)
        math = self.create_subject('Math B5 Repeat', 'MB5R', is_core=True)
        self.create_class_subject(basic_class, math)

        # Create student with enrollment and subject enrollment
        student = self.create_student('RepeatStudent', 'STU-022', class_obj=basic_class)
        self.create_enrollment(student, basic_class)
        StudentSubjectEnrollment.enroll_student_in_class_subjects(student, basic_class)

        original_enrollment = StudentSubjectEnrollment.objects.get(
            student=student,
            class_subject__class_assigned=basic_class
        )
        original_pk = original_enrollment.pk

        # Repeat student
        self.client.post(
            reverse('academics:class_promote', args=[basic_class.pk]),
            {
                f'action_{student.pk}': 'repeat',
            }
        )

        # Subject enrollment should still be active (same class)
        original_enrollment.refresh_from_db()
        self.assertTrue(original_enrollment.is_active)

    def test_graduate_deactivates_subject_enrollments(self):
        """Test that graduating a student deactivates subject enrollments."""
        # Create final year class
        shs3 = self.create_class(Class.LevelType.SHS, 3, programme=self.programme)
        core = self.create_subject('SHS3 Core', 'S3C', is_core=True)
        self.create_class_subject(shs3, core)

        # Create student with enrollment
        student = self.create_student('GradStudent', 'STU-023', class_obj=shs3)
        self.create_enrollment(student, shs3)
        StudentSubjectEnrollment.enroll_student_in_class_subjects(student, shs3)

        # Graduate student
        self.client.post(
            reverse('academics:class_promote', args=[shs3.pk]),
            {
                f'action_{student.pk}': 'graduate',
            }
        )

        # Subject enrollment should be deactivated
        enrollment = StudentSubjectEnrollment.objects.get(
            student=student,
            class_subject__class_assigned=shs3
        )
        self.assertFalse(enrollment.is_active)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class EnrollmentIntegrationTests(AcademicsTestCase):
    """Integration tests for the complete enrollment workflow."""

    def test_full_student_lifecycle_basic_school(self):
        """Test complete student lifecycle in Basic school."""
        # Create classes
        b1 = self.create_class(Class.LevelType.BASIC, 1)
        b2 = self.create_class(Class.LevelType.BASIC, 2)

        # Create subjects for both classes
        math_b1 = self.create_subject('Math B1 Int', 'MB1I', is_core=True)
        english_b1 = self.create_subject('English B1 Int', 'EB1I', is_core=False)
        math_b2 = self.create_subject('Math B2 Int', 'MB2I', is_core=True)

        self.create_class_subject(b1, math_b1)
        self.create_class_subject(b1, english_b1)
        self.create_class_subject(b2, math_b2)

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

        # 3. Promote to B2
        self.client.post(
            reverse('academics:class_promote', args=[b1.pk]),
            {
                f'action_{student.pk}': 'promote',
                f'target_class_{student.pk}': str(b2.pk),
            }
        )

        student.refresh_from_db()
        self.assertEqual(student.current_class, b2)

        # B1 enrollments should be inactive
        b1_enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            class_subject__class_assigned=b1,
            is_active=True
        )
        self.assertEqual(b1_enrollments.count(), 0)

        # B2 enrollments should be active
        b2_enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            class_subject__class_assigned=b2,
            is_active=True
        )
        self.assertEqual(b2_enrollments.count(), 1)

    def test_full_student_lifecycle_shs_with_electives(self):
        """Test complete SHS student lifecycle with elective selection."""
        # Create SHS classes
        shs1 = self.create_class(Class.LevelType.SHS, 1, programme=self.programme)

        # Create subjects
        core_math = self.create_subject('Core Math SHS', 'CMS', is_core=True)
        core_eng = self.create_subject('Core English SHS', 'CES', is_core=True)
        elec_french = self.create_subject('French SHS', 'FRS', is_core=False)
        elec_spanish = self.create_subject('Spanish SHS', 'SPS', is_core=False)

        cs_math = self.create_class_subject(shs1, core_math)
        cs_eng = self.create_class_subject(shs1, core_eng)
        cs_french = self.create_class_subject(shs1, elec_french)
        cs_spanish = self.create_class_subject(shs1, elec_spanish)

        # 1. Enroll student
        student = self.create_student('SHSLifecycle', 'STU-025')

        self.client.post(
            reverse('academics:class_student_enroll', args=[shs1.pk]),
            {'students': [student.pk]}
        )

        # Should only have core subjects (2)
        enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            is_active=True
        )
        self.assertEqual(enrollments.count(), 2)

        # 2. Manually add elective (French)
        self.client.post(
            reverse('academics:class_student_electives', args=[shs1.pk, student.pk]),
            {'electives': [cs_french.pk]}
        )

        # Should now have 3 subjects (2 core + 1 elective)
        enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            is_active=True
        )
        self.assertEqual(enrollments.count(), 3)

        # Verify French is enrolled, Spanish is not
        enrolled_codes = list(enrollments.values_list(
            'class_subject__subject__code', flat=True
        ))
        self.assertIn('CMS', enrolled_codes)
        self.assertIn('CES', enrolled_codes)
        self.assertIn('FRS', enrolled_codes)
        self.assertNotIn('SPS', enrolled_codes)
