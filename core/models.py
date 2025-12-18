from django.db import models
from django.core.cache import cache
import math


def hex_to_oklch_values(hex_color):
    """
    Convert hex color to OKLCH values string for CSS.
    Returns format: "L% C H" (e.g., "54% 0.2 260")
    """
    # Remove # if present
    hex_color = hex_color.lstrip('#')

    # Convert hex to RGB (0-1 range)
    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255

    # Convert RGB to linear RGB
    def to_linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r_lin = to_linear(r)
    g_lin = to_linear(g)
    b_lin = to_linear(b)

    # Convert to XYZ (D65)
    x = 0.4124564 * r_lin + 0.3575761 * g_lin + 0.1804375 * b_lin
    y = 0.2126729 * r_lin + 0.7151522 * g_lin + 0.0721750 * b_lin
    z = 0.0193339 * r_lin + 0.1191920 * g_lin + 0.9503041 * b_lin

    # Convert XYZ to OKLab
    l_ = 0.8189330101 * x + 0.3618667424 * y - 0.1288597137 * z
    m_ = 0.0329845436 * x + 0.9293118715 * y + 0.0361456387 * z
    s_ = 0.0482003018 * x + 0.2643662691 * y + 0.6338517070 * z

    l_ = l_ ** (1/3) if l_ >= 0 else -((-l_) ** (1/3))
    m_ = m_ ** (1/3) if m_ >= 0 else -((-m_) ** (1/3))
    s_ = s_ ** (1/3) if s_ >= 0 else -((-s_) ** (1/3))

    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_val = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_

    # Convert OKLab to OKLCH
    C = math.sqrt(a * a + b_val * b_val)
    H = math.degrees(math.atan2(b_val, a))
    if H < 0:
        H += 360

    # Format for CSS: "L% C H"
    L_percent = round(L * 100)
    C_rounded = round(C, 3)
    H_rounded = round(H)

    return f"{L_percent}% {C_rounded} {H_rounded}"


class SchoolSettings(models.Model):
    """
    Stores configuration specific to this School (Tenant).
    """
    # Branding
    logo = models.ImageField(upload_to='school_logos/', blank=True, null=True)
    favicon = models.ImageField(upload_to='school_favicons/', blank=True, null=True)
    display_name = models.CharField(max_length=50, blank=True)
    motto = models.CharField(max_length=200, blank=True)

    # Visual Identity - Colors (stored as HEX)
    primary_color = models.CharField(max_length=7, default="#4F46E5", help_text="Main brand color")
    secondary_color = models.CharField(max_length=7, default="#7C3AED", help_text="Secondary brand color")
    accent_color = models.CharField(max_length=7, default="#F59E0B", help_text="Accent/highlight color")

    # OKLCH values (auto-generated, not editable)
    primary_color_oklch = models.CharField(max_length=50, blank=True, editable=False)
    secondary_color_oklch = models.CharField(max_length=50, blank=True, editable=False)
    accent_color_oklch = models.CharField(max_length=50, blank=True, editable=False)

    def save(self, *args, **kwargs):
        self.pk = 1
        # Convert HEX colors to OKLCH for DaisyUI theming
        if self.primary_color:
            self.primary_color_oklch = hex_to_oklch_values(self.primary_color)
        if self.secondary_color:
            self.secondary_color_oklch = hex_to_oklch_values(self.secondary_color)
        if self.accent_color:
            self.accent_color_oklch = hex_to_oklch_values(self.accent_color)
        super().save(*args, **kwargs)
        cache.delete('school_profile')

    @classmethod
    def load(cls):
        profile = cache.get('school_profile')
        if profile is None:
            profile, created = cls.objects.get_or_create(pk=1)
            cache.set('school_profile', profile, 60*60*24)
        return profile

    class Meta:
        verbose_name = "School Settings"
        verbose_name_plural = "School Settings"

    def __str__(self):
        return "School Profile & Settings"
