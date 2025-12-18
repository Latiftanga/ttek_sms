from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

class UserManager(BaseUserManager):
    """
    Custom manager to easily create different types of school users.
    """

    def create_user(self, email, password=None, **extra_fields):
        """Base method for creating a generic user."""
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create a Superuser (Platform Owner)."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)

    # --- ROLE SPECIFIC HELPERS ---

    def create_school_admin(self, email, password=None, **extra_fields):
        """Create a School Administrator (Principal/Head)."""
        extra_fields.setdefault('is_school_admin', True)
        # School admins usually need access to the school-level dashboard, but NOT the public admin
        extra_fields.setdefault('is_staff', False) 
        return self.create_user(email, password, **extra_fields)

    def create_teacher(self, email, password=None, **extra_fields):
        """Create a Teacher."""
        extra_fields.setdefault('is_teacher', True)
        return self.create_user(email, password, **extra_fields)

    def create_student(self, email, password=None, **extra_fields):
        """Create a Student."""
        extra_fields.setdefault('is_student', True)
        return self.create_user(email, password, **extra_fields)

    def create_parent(self, email, password=None, **extra_fields):
        """Create a Parent."""
        extra_fields.setdefault('is_parent', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(_('email address'), unique=True)

    # Roles / Flags
    is_school_admin = models.BooleanField(default=False)
    is_teacher = models.BooleanField(default=False)
    is_student = models.BooleanField(default=False)
    is_parent = models.BooleanField(default=False)  # <--- Added this

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email
    
    @property
    def role_label(self):
        """Helper to get a string representation of the user's role"""
        if self.is_superuser: return "Super Admin"
        if self.is_school_admin: return "School Admin"
        if self.is_teacher: return "Teacher"
        if self.is_student: return "Student"
        if self.is_parent: return "Parent"
        return "User"