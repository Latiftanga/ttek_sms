import math
from io import BytesIO
from django.db import models
from django.core.files.base import ContentFile
from django_tenants.models import TenantMixin, DomainMixin
from PIL import Image, UnidentifiedImageError
from core.storage import PublicSchemaStorage
import logging

logger = logging.getLogger(__name__)

# Image size limits
LOGO_MAX_SIZE = (256, 256)
FAVICON_MAX_SIZE = (64, 64)


def hex_to_oklch_values(hex_color):
    """
    Convert hex color to OKLCH values string for CSS.
    Returns format: "L% C H" (e.g., "54% 0.2 260")
    """
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255

    def to_linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r_lin, g_lin, b_lin = to_linear(r), to_linear(g), to_linear(b)

    x = 0.4124564 * r_lin + 0.3575761 * g_lin + 0.1804375 * b_lin
    y = 0.2126729 * r_lin + 0.7151522 * g_lin + 0.0721750 * b_lin
    z = 0.0193339 * r_lin + 0.1191920 * g_lin + 0.9503041 * b_lin

    l_ = 0.8189330101 * x + 0.3618667424 * y - 0.1288597137 * z
    m_ = 0.0329845436 * x + 0.9293118715 * y + 0.0361456387 * z
    s_ = 0.0482003018 * x + 0.2643662691 * y + 0.6338517070 * z

    l_ = l_ ** (1/3) if l_ >= 0 else -((-l_) ** (1/3))
    m_ = m_ ** (1/3) if m_ >= 0 else -((-m_) ** (1/3))
    s_ = s_ ** (1/3) if s_ >= 0 else -((-s_) ** (1/3))

    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_val = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_

    C = math.sqrt(a * a + b_val * b_val)
    H = math.degrees(math.atan2(b_val, a))
    if H < 0:
        H += 360

    return f"{round(L * 100)}% {round(C, 3)} {round(H)}"


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

    # All available level types that can be enabled
    ALL_LEVEL_TYPES = [
        ('creche', 'Creche'),
        ('nursery', 'Nursery'),
        ('kg', 'Kindergarten'),
        ('basic', 'Basic (Primary & JHS)'),
        ('shs', 'SHS'),
    ]

    # Basic Info
    name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=20, help_text="Short name for sidebar display")
    motto = models.CharField(max_length=200, help_text="School motto")
    is_active = models.BooleanField(default=True, help_text="Inactive schools cannot be accessed")
    education_system = models.CharField(
        max_length=10,
        choices=EDUCATION_SYSTEM_CHOICES,
        default='both',
        help_text="Determines which educational levels and features are available"
    )
    enabled_levels = models.JSONField(
        default=list,
        blank=True,
        help_text="Specific levels offered (e.g., ['basic', 'shs']). If empty, defaults based on education_system."
    )

    # Branding - use PublicSchemaStorage so URLs work from any tenant context
    logo = models.ImageField(
        upload_to='school_logos/',
        storage=PublicSchemaStorage(),
        blank=True,
        null=True,
        help_text="School logo/crest"
    )
    favicon = models.ImageField(
        upload_to='school_favicons/',
        storage=PublicSchemaStorage(),
        blank=True,
        null=True,
        help_text="Browser tab icon"
    )

    # Theme Colors (HEX format)
    primary_color = models.CharField(max_length=7, default="#4F46E5", help_text="Main brand color (hex)")
    secondary_color = models.CharField(max_length=7, default="#7C3AED", help_text="Secondary brand color (hex)")
    accent_color = models.CharField(max_length=7, default="#F59E0B", help_text="Accent/highlight color (hex)")

    # OKLCH values (auto-generated for CSS, not editable)
    primary_color_oklch = models.CharField(max_length=50, blank=True, editable=False)
    secondary_color_oklch = models.CharField(max_length=50, blank=True, editable=False)
    accent_color_oklch = models.CharField(max_length=50, blank=True, editable=False)

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

    def _resize_image(self, image_field, max_size):
        """Resize an image field to max dimensions, preserving transparency."""
        if not image_field or not hasattr(image_field, 'file'):
            return

        try:
            img = Image.open(image_field)

            # Handle RGBA/transparency for logos/favicons - keep as PNG
            if img.mode in ('RGBA', 'LA', 'P'):
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                buffer = BytesIO()
                img.save(buffer, format='PNG', optimize=True)
                buffer.seek(0)
                filename = image_field.name.rsplit('.', 1)[0].rsplit('/', 1)[-1] + '.png'
                image_field.save(filename, ContentFile(buffer.read()), save=False)
            else:
                # Convert to WebP for non-transparent images
                img = img.convert('RGB')
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                buffer = BytesIO()
                img.save(buffer, format='WEBP', quality=85, optimize=True)
                buffer.seek(0)
                filename = image_field.name.rsplit('.', 1)[0].rsplit('/', 1)[-1] + '.webp'
                image_field.save(filename, ContentFile(buffer.read()), save=False)
        except (UnidentifiedImageError, Exception) as e:
            logger.warning(f"Could not process image: {e}")

    def save(self, *args, **kwargs):
        # Resize logo and favicon if uploaded
        if self.logo and hasattr(self.logo, 'file'):
            self._resize_image(self.logo, LOGO_MAX_SIZE)
        if self.favicon and hasattr(self.favicon, 'file'):
            self._resize_image(self.favicon, FAVICON_MAX_SIZE)

        # Convert HEX colors to OKLCH for DaisyUI theming
        if self.primary_color:
            self.primary_color_oklch = hex_to_oklch_values(self.primary_color)
        if self.secondary_color:
            self.secondary_color_oklch = hex_to_oklch_values(self.secondary_color)
        if self.accent_color:
            self.accent_color_oklch = hex_to_oklch_values(self.accent_color)

        super().save(*args, **kwargs)

    @property
    def logo_url(self):
        """Return logo URL if available."""
        return self.logo.url if self.logo else None

    @property
    def favicon_url(self):
        """Return favicon URL if available."""
        return self.favicon.url if self.favicon else None

    @property
    def display_name(self):
        """Return short_name if available, otherwise name."""
        return self.short_name or self.name

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
        if self.enabled_levels:
            return 'shs' in self.enabled_levels
        return self.education_system in ('shs', 'both')

    @property
    def has_programmes(self):
        """Programmes are used in SHS schools."""
        if self.enabled_levels:
            return 'shs' in self.enabled_levels
        return self.education_system in ('shs', 'both')

    def get_allowed_level_types(self):
        """
        Return list of allowed level types based on enabled_levels or education_system.
        If enabled_levels is configured, use that. Otherwise fall back to education_system.
        Returns tuples of (value, display_name).
        """
        # If specific levels are configured, use them
        if self.enabled_levels:
            level_map = dict(self.ALL_LEVEL_TYPES)
            return [
                (level, level_map.get(level, level.title()))
                for level in self.enabled_levels
                if level in level_map
            ]

        # Fall back to education_system-based defaults
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