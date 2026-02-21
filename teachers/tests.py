from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from teachers.models import Teacher, TeacherInvitation, Promotion, Qualification

User = get_user_model()


class TeacherModelTests(TenantTestCase):
    """Tests for the Teacher model."""

    def _create_teacher(self, **kwargs):
        defaults = {
            'first_name': 'Kwame',
            'last_name': 'Asante',
            'date_of_birth': date(1985, 3, 15),
            'gender': 'M',
            'staff_id': 'TCH-001',
            'employment_date': date(2020, 9, 1),
        }
        defaults.update(kwargs)
        return Teacher.objects.create(**defaults)

    def test_create_teacher(self):
        teacher = self._create_teacher()
        self.assertEqual(teacher.first_name, 'Kwame')
        self.assertEqual(teacher.status, Teacher.Status.ACTIVE)

    def test_full_name(self):
        teacher = self._create_teacher(middle_name='Kwesi')
        self.assertEqual(teacher.full_name, 'Kwame Kwesi Asante')

    def test_full_name_no_middle(self):
        teacher = self._create_teacher()
        self.assertEqual(teacher.full_name, 'Kwame Asante')

    def test_str(self):
        teacher = self._create_teacher(title='mr')
        self.assertIn('Kwame', str(teacher))
        self.assertIn('Asante', str(teacher))

    def test_current_rank_no_promotions(self):
        teacher = self._create_teacher()
        self.assertEqual(teacher.current_rank, '\u2014')

    def test_current_rank_with_promotion(self):
        teacher = self._create_teacher()
        Promotion.objects.create(
            teacher=teacher,
            rank=Promotion.Rank.SUPERINTENDENT_II,
            date_promoted=date(2020, 9, 1),
        )
        self.assertNotEqual(teacher.current_rank, '\u2014')

    def test_staff_category_default(self):
        teacher = self._create_teacher()
        self.assertEqual(teacher.staff_category, Teacher.StaffCategory.TEACHING)

    def test_unique_staff_id(self):
        self._create_teacher(staff_id='TCH-001')
        with self.assertRaises(Exception):
            self._create_teacher(staff_id='TCH-001', first_name='Ama')

    def test_user_link(self):
        user = User.objects.create_teacher(
            email='kwame@school.com', password='pass123'
        )
        teacher = self._create_teacher(user=user)
        self.assertEqual(teacher.user, user)


class TeacherInvitationModelTests(TenantTestCase):
    """Tests for the TeacherInvitation model."""

    def setUp(self):
        self.teacher = Teacher.objects.create(
            first_name='Ama',
            last_name='Mensah',
            date_of_birth=date(1990, 6, 15),
            gender='F',
            staff_id='TCH-002',
            email='ama@school.com',
        )

    def test_create_invitation(self):
        inv = TeacherInvitation.objects.create(
            teacher=self.teacher,
            email='ama@school.com',
        )
        self.assertEqual(inv.status, TeacherInvitation.Status.PENDING)
        self.assertIsNotNone(inv.token)
        self.assertIsNotNone(inv.expires_at)

    def test_token_auto_generated(self):
        inv = TeacherInvitation.objects.create(
            teacher=self.teacher,
            email='ama@school.com',
        )
        self.assertTrue(len(inv.token) > 20)

    def test_is_valid_pending_not_expired(self):
        inv = TeacherInvitation.objects.create(
            teacher=self.teacher,
            email='ama@school.com',
            expires_at=timezone.now() + timedelta(hours=72),
        )
        self.assertTrue(inv.is_valid)

    def test_is_expired(self):
        inv = TeacherInvitation.objects.create(
            teacher=self.teacher,
            email='ama@school.com',
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.assertTrue(inv.is_expired)
        self.assertFalse(inv.is_valid)

    def test_mark_accepted(self):
        inv = TeacherInvitation.objects.create(
            teacher=self.teacher,
            email='ama@school.com',
        )
        inv.mark_accepted()
        inv.refresh_from_db()
        self.assertEqual(inv.status, TeacherInvitation.Status.ACCEPTED)
        self.assertIsNotNone(inv.accepted_at)

    def test_mark_expired(self):
        inv = TeacherInvitation.objects.create(
            teacher=self.teacher,
            email='ama@school.com',
        )
        inv.mark_expired()
        inv.refresh_from_db()
        self.assertEqual(inv.status, TeacherInvitation.Status.EXPIRED)

    def test_cancel(self):
        inv = TeacherInvitation.objects.create(
            teacher=self.teacher,
            email='ama@school.com',
        )
        inv.cancel()
        inv.refresh_from_db()
        self.assertEqual(inv.status, TeacherInvitation.Status.CANCELLED)

    def test_create_for_teacher_cancels_existing(self):
        inv1 = TeacherInvitation.create_for_teacher(
            self.teacher, 'ama@school.com'
        )
        inv2 = TeacherInvitation.create_for_teacher(
            self.teacher, 'ama@school.com'
        )
        inv1.refresh_from_db()
        self.assertEqual(inv1.status, TeacherInvitation.Status.CANCELLED)
        self.assertEqual(inv2.status, TeacherInvitation.Status.PENDING)

    def test_get_by_token_valid(self):
        inv = TeacherInvitation.create_for_teacher(
            self.teacher, 'ama@school.com'
        )
        found = TeacherInvitation.get_by_token(inv.token)
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, inv.pk)

    def test_get_by_token_expired(self):
        inv = TeacherInvitation.objects.create(
            teacher=self.teacher,
            email='ama@school.com',
            expires_at=timezone.now() - timedelta(hours=1),
        )
        found = TeacherInvitation.get_by_token(inv.token)
        self.assertIsNone(found)

    def test_get_by_token_nonexistent(self):
        found = TeacherInvitation.get_by_token('nonexistent-token')
        self.assertIsNone(found)

    def test_generate_token_uniqueness(self):
        tokens = {TeacherInvitation.generate_token() for _ in range(50)}
        self.assertEqual(len(tokens), 50)


class PromotionModelTests(TenantTestCase):
    """Tests for the Promotion model."""

    def setUp(self):
        self.teacher = Teacher.objects.create(
            first_name='Kofi',
            last_name='Boateng',
            date_of_birth=date(1988, 1, 10),
            gender='M',
            staff_id='TCH-003',
        )

    def test_create_promotion(self):
        promo = Promotion.objects.create(
            teacher=self.teacher,
            rank=Promotion.Rank.SUPERINTENDENT_II,
            date_promoted=date(2020, 1, 1),
        )
        self.assertIn('Superintendent II', str(promo))

    def test_ordering_latest_first(self):
        Promotion.objects.create(
            teacher=self.teacher,
            rank=Promotion.Rank.SUPERINTENDENT_II,
            date_promoted=date(2020, 1, 1),
        )
        Promotion.objects.create(
            teacher=self.teacher,
            rank=Promotion.Rank.SUPERINTENDENT_I,
            date_promoted=date(2023, 1, 1),
        )
        latest = self.teacher.promotions.first()
        self.assertEqual(latest.rank, Promotion.Rank.SUPERINTENDENT_I)


class QualificationModelTests(TenantTestCase):
    """Tests for the Qualification model."""

    def setUp(self):
        self.teacher = Teacher.objects.create(
            first_name='Abena',
            last_name='Osei',
            date_of_birth=date(1992, 7, 20),
            gender='F',
            staff_id='TCH-004',
        )

    def test_create_qualification(self):
        qual = Qualification.objects.create(
            teacher=self.teacher,
            title='B.Ed Mathematics',
            institution='University of Cape Coast',
            date_started=date(2010, 9, 1),
            date_ended=date(2014, 7, 1),
            status=Qualification.Status.COMPLETED,
        )
        self.assertIn('B.Ed Mathematics', str(qual))

    def test_default_status_completed(self):
        qual = Qualification.objects.create(
            teacher=self.teacher,
            title='M.Phil Education',
            institution='UEW',
        )
        self.assertEqual(qual.status, Qualification.Status.COMPLETED)
