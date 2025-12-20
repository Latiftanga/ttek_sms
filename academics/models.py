from django.db import models
from django.utils.translation import gettext_lazy as _


class Programme(models.Model):
    """
    SHS Programmes (General Arts, Business, Science, etc.)
    Only applicable to SHS level.
    """
    name = models.CharField(
        max_length=100,
        help_text="e.g., General Arts, Business, Science"
    )
    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="e.g., ART, BUS, SCI"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Programme"
        verbose_name_plural = "Programmes"

    def __str__(self):
        return self.name


class Class(models.Model):
    """
    Represents a class/classroom grouping of students.

    For Basic (KG, Primary, JHS):
        - Name format: B1-A, B1-B, JHS2-A, KG1-A

    For SHS:
        - Name auto-generated: Level + Programme Code + Section
        - Example: 1ART-A, 2BUS-B, 3SCI-A
    """
    class LevelType(models.TextChoices):
        KG = 'kg', _('Kindergarten')
        PRIMARY = 'primary', _('Primary')
        JHS = 'jhs', _('JHS')
        SHS = 'shs', _('SHS')

    # Level info
    level_type = models.CharField(
        max_length=10,
        choices=LevelType.choices,
        default=LevelType.PRIMARY
    )
    level_number = models.PositiveSmallIntegerField(
        help_text="1, 2, 3, etc."
    )
    section = models.CharField(
        max_length=5,
        help_text="A, B, C, etc."
    )

    # SHS specific
    programme = models.ForeignKey(
        Programme,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='classes',
        help_text="Required for SHS only"
    )

    # Auto-generated class name
    name = models.CharField(
        max_length=20,
        editable=False,
        help_text="Auto-generated: B1-A, JHS2-B, 1ART-A"
    )

    capacity = models.PositiveIntegerField(
        default=35,
        help_text="Maximum number of students"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['level_type', 'level_number', 'programme', 'section']
        verbose_name = "Class"
        verbose_name_plural = "Classes"
        unique_together = ['level_type', 'level_number', 'programme', 'section']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = self.generate_name()
        super().save(*args, **kwargs)

    def generate_name(self):
        """Generate class name based on level type."""
        if self.level_type == self.LevelType.KG:
            return f"KG{self.level_number}-{self.section}"
        elif self.level_type == self.LevelType.PRIMARY:
            return f"B{self.level_number}-{self.section}"
        elif self.level_type == self.LevelType.JHS:
            # JHS is B7-B9, so add 6 to get actual Basic number
            basic_num = self.level_number + 6
            return f"B{basic_num}-{self.section}"
        elif self.level_type == self.LevelType.SHS:
            # SHS: 1ART-A, 2BUS-B format
            prog_code = self.programme.code if self.programme else "GEN"
            return f"{self.level_number}{prog_code}-{self.section}"
        return f"{self.level_type.upper()}{self.level_number}-{self.section}"

    @property
    def level_display(self):
        """Human-readable level name."""
        if self.level_type == self.LevelType.KG:
            return f"KG {self.level_number}"
        elif self.level_type == self.LevelType.PRIMARY:
            return f"Basic {self.level_number}"
        elif self.level_type == self.LevelType.JHS:
            return f"JHS {self.level_number}"
        elif self.level_type == self.LevelType.SHS:
            return f"SHS {self.level_number}"
        return str(self.level_number)

    @classmethod
    def get_by_level_type(cls, level_type):
        """Get all classes of a specific level type."""
        return cls.objects.filter(level_type=level_type, is_active=True)


class Subject(models.Model):
    """
    Represents a subject taught at the school.
    Subjects can be core (mandatory) or elective.
    """
    name = models.CharField(
        max_length=100,
        help_text="e.g., Mathematics, English Language, Integrated Science"
    )
    short_name = models.CharField(
        max_length=20,
        help_text="e.g., MATH, ENG, INT SCI"
    )
    code = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional subject code"
    )
    description = models.TextField(blank=True)
    is_core = models.BooleanField(
        default=True,
        help_text="Core subjects are mandatory"
    )
    # Which level types this subject applies to
    for_kg = models.BooleanField(default=False, verbose_name="KG")
    for_primary = models.BooleanField(default=True, verbose_name="Primary")
    for_jhs = models.BooleanField(default=True, verbose_name="JHS")
    for_shs = models.BooleanField(default=False, verbose_name="SHS")

    # SHS subjects can be programme-specific
    programmes = models.ManyToManyField(
        Programme,
        blank=True,
        related_name='subjects',
        help_text="For SHS electives: which programmes offer this subject"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_core', 'name']
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"

    def __str__(self):
        return self.name

    @property
    def applicable_levels(self):
        """Return list of level types this subject applies to."""
        levels = []
        if self.for_kg:
            levels.append('KG')
        if self.for_primary:
            levels.append('Primary')
        if self.for_jhs:
            levels.append('JHS')
        if self.for_shs:
            levels.append('SHS')
        return levels
