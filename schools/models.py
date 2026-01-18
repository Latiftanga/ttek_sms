from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Region(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True, help_text="Short code e.g. UW, GA")

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class District(models.Model):
    name = models.CharField(max_length=100)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='districts')

    def __str__(self):
        return f"{self.name} ({self.region.code})"

    class Meta:
        unique_together = ('name', 'region') # Prevent duplicate districts in same region
        ordering = ['name']


class School(TenantMixin):
    EDUCATION_SYSTEM_CHOICES = [
        ('basic', 'Basic Only (Creche - Basic 9)'),
        ('shs', 'SHS Only'),
        ('both', 'Both Basic and SHS'),
    ]

    # Basic Info
    name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=20, blank=True, help_text="Short name for sidebar display")
    education_system = models.CharField(
        max_length=10,
        choices=EDUCATION_SYSTEM_CHOICES,
        default='both',
        help_text="Determines which educational levels and features are available"
    )

    # Contact & Address
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    digital_address = models.CharField(max_length=50, blank=True, help_text="e.g., GA-123-4567")
    city = models.CharField(max_length=100, blank=True)

    # Location - linked to Region and District models
    location_region = models.ForeignKey(
        'Region',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schools',
        verbose_name='Region',
        help_text="Select the region where the school is located"
    )
    location_district = models.ForeignKey(
        'District',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schools',
        verbose_name='District',
        help_text="Select the district within the region"
    )

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

    @property
    def is_basic_school(self):
        """Check if this is a basic-only school."""
        return self.education_system == 'basic'

    @property
    def is_shs_school(self):
        """Check if this is an SHS-only school."""
        return self.education_system == 'shs'

    @property
    def has_basic_levels(self):
        """Check if school supports basic education levels."""
        return self.education_system in ('basic', 'both')

    @property
    def has_shs_levels(self):
        """Check if school supports SHS levels."""
        return self.education_system in ('shs', 'both')

    @property
    def has_houses(self):
        """Houses/dormitories are used in SHS boarding schools."""
        return self.education_system in ('shs', 'both')

    @property
    def has_programmes(self):
        """Programmes are used in SHS schools."""
        return self.education_system in ('shs', 'both')

    def get_allowed_level_types(self):
        """
        Return list of allowed level types based on education_system.
        Returns tuples of (value, display_name).
        """
        basic_levels = [
            ('creche', 'Creche'),
            ('nursery', 'Nursery'),
            ('kg', 'Kindergarten'),
            ('basic', 'Basic'),
        ]
        shs_levels = [
            ('shs', 'SHS'),
        ]

        if self.education_system == 'basic':
            return basic_levels
        elif self.education_system == 'shs':
            return shs_levels
        else:  # 'both'
            return basic_levels + shs_levels

    @property
    def education_system_display(self):
        """Return the display name for the education system."""
        return dict(self.EDUCATION_SYSTEM_CHOICES).get(self.education_system, 'Both Basic and SHS')


class Domain(DomainMixin):
    pass