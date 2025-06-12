from django.db import models
from django.contrib.auth.models import BaseUserManager
import string
import secrets


class TenantAwareManager(models.Manager):
    """Manager for tenant-aware models"""

    def for_school(self, school):
        """Filter queryset by school"""
        return self.get_queryset().filter(school=school)

    def active_for_school(self, school):
        """Filter active records for a school"""
        return self.get_queryset().filter(school=school, is_active=True)


class TenantManager(models.Manager):
    """Manager for tenant operations"""

    def get_by_domain(self, domain):
        """Get tenant by domain or subdomain"""
        # First try exact domain match
        try:
            return self.get(domain=domain, is_active=True)
        except self.model.DoesNotExist:
            pass

        # Try subdomain match
        if '.' in domain:
            subdomain = domain.split('.')[0]
            try:
                return self.get(subdomain=subdomain, is_active=True)
            except self.model.DoesNotExist:
                pass

        raise self.model.DoesNotExist(
            f"No active tenant found for domain: {domain}")


class UserManager(BaseUserManager):
    """Manager for users"""

    def create_user(self, username, password=None, school=None, **extra_fields):
        """Create, save and return new user"""
        if not username:
            raise ValueError('User must have a username')

        # For non-superusers, school is required
        if not extra_fields.get('is_superuser', False) and not school:
            raise ValueError('Non-superuser accounts must belong to a school')

        user = self.model(username=username, school=school, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password, **extra_fields):
        """Create and return a new superuser"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        # Superusers don't need a school
        return self.create_user(username, password, school=None, **extra_fields)

    def create_adminuser(self, username, password, school):
        """Create and return a new school admin user"""
        if not school:
            raise ValueError('Admin user must belong to a school')

        user = self.create_user(
            username=username,
            password=password,
            school=school,
            is_staff=True,
            is_admin=True,
            is_teacher=True  # School admins can also act as teachers
        )
        return user

    def create_teacheruser(self, username, school):
        """Create and return a new teacher user"""
        if not school:
            raise ValueError('Teacher user must belong to a school')

        # Generate random password
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(8))

        user = self.create_user(
            username=username,
            password=password,
            school=school,
            is_teacher=True
        )
        return user, password

    def create_studentuser(self, username, school):
        """Create and return a new student user"""
        if not school:
            raise ValueError('Student user must belong to a school')

        # Generate random password
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(8))

        user = self.create_user(
            username=username,
            password=password,
            school=school,
            is_student=True
        )
        return user, password
