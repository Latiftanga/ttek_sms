from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class School(TenantMixin):
    # Basic Info
    name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=20, blank=True, help_text="Short name for sidebar display")

    # Contact & Address
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    digital_address = models.CharField(max_length=50, blank=True, help_text="e.g., GA-123-4567")
    city = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)

    # Administration
    headmaster_name = models.CharField(max_length=100, blank=True, verbose_name="Head's Name")
    headmaster_title = models.CharField(max_length=50, blank=True, default="Headmaster", verbose_name="Head's Title")

    # Metadata
    created_on = models.DateField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    auto_create_schema = True

    def __str__(self):
        return self.name

    @property
    def display_name(self):
        """Return short_name if available, otherwise name."""
        return self.short_name or self.name

    @property
    def logo_url(self):
        """Return logo URL if available."""
        if self.logo:
            return self.logo.url
        return None


class Domain(DomainMixin):
    pass