from django.test import TestCase
from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase

User = get_user_model()


class UserManagerTests(TestCase):
    """Tests for the custom UserManager (public schema)."""

    def test_create_user(self):
        """Test creating a regular user with email."""
        user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.assertEqual(user.email, 'test@example.com')
        self.assertTrue(user.check_password('testpass123'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_create_user_without_email_raises_error(self):
        """Test that creating a user without email raises ValueError."""
        with self.assertRaises(ValueError):
            User.objects.create_user(email='', password='testpass123')

    def test_create_user_normalizes_email(self):
        """Test that email is normalized (lowercase domain)."""
        user = User.objects.create_user(
            email='test@EXAMPLE.COM',
            password='testpass123'
        )
        self.assertEqual(user.email, 'test@example.com')

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123'
        )
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_create_superuser_without_is_staff_raises_error(self):
        """Test that superuser must have is_staff=True."""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email='admin@example.com',
                password='adminpass123',
                is_staff=False
            )

    def test_create_superuser_without_is_superuser_raises_error(self):
        """Test that superuser must have is_superuser=True."""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email='admin@example.com',
                password='adminpass123',
                is_superuser=False
            )


class TenantUserManagerTests(TenantTestCase):
    """Tests for the custom UserManager (tenant schema)."""

    def test_create_school_admin(self):
        """Test creating a school admin."""
        user = User.objects.create_school_admin(
            email='principal@school.com',
            password='schoolpass123'
        )
        self.assertTrue(user.is_school_admin)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_teacher)
        self.assertFalse(user.is_student)
        self.assertFalse(user.is_parent)

    def test_create_teacher(self):
        """Test creating a teacher."""
        user = User.objects.create_teacher(
            email='teacher@school.com',
            password='teacherpass123'
        )
        self.assertTrue(user.is_teacher)
        self.assertFalse(user.is_school_admin)
        self.assertFalse(user.is_student)
        self.assertFalse(user.is_parent)

    def test_create_student(self):
        """Test creating a student."""
        user = User.objects.create_student(
            email='student@school.com',
            password='studentpass123'
        )
        self.assertTrue(user.is_student)
        self.assertFalse(user.is_school_admin)
        self.assertFalse(user.is_teacher)
        self.assertFalse(user.is_parent)

    def test_create_parent(self):
        """Test creating a parent."""
        user = User.objects.create_parent(
            email='parent@example.com',
            password='parentpass123'
        )
        self.assertTrue(user.is_parent)
        self.assertFalse(user.is_school_admin)
        self.assertFalse(user.is_teacher)
        self.assertFalse(user.is_student)


class UserModelTests(TestCase):
    """Tests for the User model (public schema)."""

    def test_user_str_returns_email(self):
        """Test that user string representation is email."""
        user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.assertEqual(str(user), 'test@example.com')

    def test_role_label_platform_admin(self):
        """Test role_label for superuser in public schema."""
        user = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123'
        )
        self.assertEqual(user.role_label, 'Platform Admin')

    def test_role_label_platform_user(self):
        """Test role_label for user with no specific role in public schema."""
        user = User.objects.create_user(
            email='user@example.com',
            password='userpass123'
        )
        self.assertEqual(user.role_label, 'Platform User')

    def test_username_field_is_email(self):
        """Test that USERNAME_FIELD is email."""
        self.assertEqual(User.USERNAME_FIELD, 'email')

    def test_username_is_none(self):
        """Test that username field is removed."""
        user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.assertFalse(hasattr(user, 'username') and user.username)


class TenantUserModelTests(TenantTestCase):
    """Tests for the User model (tenant schema)."""

    def test_role_label_school_admin(self):
        """Test role_label for school admin."""
        user = User.objects.create_school_admin(
            email='principal@school.com',
            password='principalpass123'
        )
        self.assertEqual(user.role_label, 'School Admin')

    def test_role_label_teacher(self):
        """Test role_label for teacher."""
        user = User.objects.create_teacher(
            email='teacher@school.com',
            password='teacherpass123'
        )
        self.assertEqual(user.role_label, 'Teacher')

    def test_role_label_student(self):
        """Test role_label for student."""
        user = User.objects.create_student(
            email='student@school.com',
            password='studentpass123'
        )
        self.assertEqual(user.role_label, 'Student')

    def test_role_label_parent(self):
        """Test role_label for parent."""
        user = User.objects.create_parent(
            email='parent@example.com',
            password='parentpass123'
        )
        self.assertEqual(user.role_label, 'Parent')
