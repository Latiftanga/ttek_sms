import uuid
from html import escape as html_escape
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
from academics.models import Subject
from students.models import Student
from core.models import Term


class GradingSystem(models.Model):
    """Defines a grading system (e.g., WASSCE, BECE, or custom system)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    SCHOOL_LEVELS = [
        ('BASIC', 'Basic School'),
        ('SHS', 'Senior High School'),
    ]

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text='Name of the grading system (e.g., WASSCE, BECE, Custom)'
    )
    level = models.CharField(
        max_length=10,
        choices=SCHOOL_LEVELS,
        help_text='School level this grading system is for'
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    # Ghana-specific configuration
    pass_mark = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Minimum percentage to pass a subject (default 50%)'
    )
    credit_mark = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Minimum percentage for a credit pass (WASSCE: 50% for C6)'
    )
    # For WASSCE aggregate calculation (best 6 subjects)
    aggregate_subjects_count = models.PositiveSmallIntegerField(
        default=6,
        help_text='Number of best subjects used for aggregate calculation (WASSCE: 6)'
    )
    # Minimum subjects to pass for promotion
    min_subjects_to_pass = models.PositiveSmallIntegerField(
        default=0,
        help_text='Minimum subjects a student must pass for promotion (0 = use average only)'
    )
    # Minimum average for promotion
    min_average_for_promotion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=40.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Minimum average percentage required for promotion'
    )
    # Core subjects requirement for promotion (Ghana: must pass all core subjects)
    require_core_pass = models.BooleanField(
        default=True,
        help_text='Require passing all core subjects for promotion (Ghana standard)'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"

    def is_passing_score(self, score):
        """Check if a score is passing based on this grading system's pass mark."""
        if score is None:
            return False
        return Decimal(str(score)) >= self.pass_mark

    def is_credit_score(self, score):
        """Check if a score qualifies for a credit pass."""
        if score is None:
            return False
        return Decimal(str(score)) >= self.credit_mark

    def get_grade_for_score(self, score):
        """Look up the grade for a given score."""
        if score is None:
            return None
        return self.scales.filter(
            min_percentage__lte=score,
            max_percentage__gte=score
        ).first()

    def calculate_aggregate(self, subject_grades):
        """
        Calculate WASSCE-style aggregate from best N subjects.
        Returns tuple of (aggregate_points, subjects_used).
        Lower aggregate is better (best possible = 6 for 6 subjects with A1).
        """
        # Get grades with aggregate points, sorted by points (best first)
        grades_with_points = [
            sg for sg in subject_grades
            if sg.total_score is not None
        ]

        if not grades_with_points:
            return None, []

        # Get aggregate points for each grade
        grade_points = []
        for sg in grades_with_points:
            grade_scale = self.get_grade_for_score(sg.total_score)
            if grade_scale and grade_scale.aggregate_points:
                grade_points.append({
                    'subject_grade': sg,
                    'points': grade_scale.aggregate_points,
                    'is_core': sg.subject.is_core
                })

        if not grade_points:
            return None, []

        # Sort by aggregate points (best first, lower is better)
        grade_points.sort(key=lambda x: x['points'])

        # Take best N subjects (default 6 for WASSCE)
        best_subjects = grade_points[:self.aggregate_subjects_count]
        aggregate = sum(gp['points'] for gp in best_subjects)

        return aggregate, [gp['subject_grade'] for gp in best_subjects]

    def check_promotion_eligibility(self, term_report):
        """
        Check if a student is eligible for promotion based on Ghana education rules.
        Returns tuple of (is_eligible, reasons).
        """
        reasons = []
        is_eligible = True

        # Check minimum average
        if term_report.average < self.min_average_for_promotion:
            is_eligible = False
            reasons.append(
                f"Average ({term_report.average:.1f}%) below required {self.min_average_for_promotion}%"
            )

        # Check minimum subjects passed
        if self.min_subjects_to_pass > 0:
            if term_report.subjects_passed < self.min_subjects_to_pass:
                is_eligible = False
                reasons.append(
                    f"Only passed {term_report.subjects_passed} subjects, "
                    f"need at least {self.min_subjects_to_pass}"
                )

        # Check core subjects requirement
        if self.require_core_pass:
            core_grades = SubjectTermGrade.objects.filter(
                student=term_report.student,
                term=term_report.term,
                subject__is_core=True
            )
            failed_core = [
                sg for sg in core_grades
                if sg.total_score is not None and not self.is_passing_score(sg.total_score)
            ]
            if failed_core:
                is_eligible = False
                failed_names = ', '.join(sg.subject.name for sg in failed_core)
                reasons.append(f"Failed core subjects: {failed_names}")

        return is_eligible, reasons

    class Meta:
        db_table = 'grading_system'
        ordering = ['level', 'name']
        verbose_name = 'Grading System'
        verbose_name_plural = 'Grading Systems'


class GradeScale(models.Model):
    """Defines a grade within a grading system (e.g., A1 = 80-100 for WASSCE)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grading_system = models.ForeignKey(
        GradingSystem,
        on_delete=models.CASCADE,
        related_name='scales',
        db_index=True
    )
    grade_label = models.CharField(
        max_length=10,
        help_text='Grade label (e.g., A1, B2, C6 for WASSCE; A, B, C for BECE)'
    )
    min_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Minimum percentage for this grade (inclusive)'
    )
    max_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Maximum percentage for this grade (inclusive)'
    )
    aggregate_points = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(9)],
        help_text='Aggregate points for WASSCE/BECE (1-9, where 1 is best)'
    )
    interpretation = models.CharField(
        max_length=50,
        blank=True,
        help_text='Grade interpretation (e.g., Excellent, Very Good, Credit, Pass, Fail)'
    )
    is_pass = models.BooleanField(
        default=True,
        help_text='Whether this grade is considered passing'
    )
    is_credit = models.BooleanField(
        default=True,
        help_text='Whether this grade is a credit pass (relevant for university admission)'
    )
    order = models.IntegerField(
        default=0,
        help_text='Display order (lower numbers appear first)'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.grade_label} ({self.min_percentage}-{self.max_percentage}%) - {self.interpretation}"

    def clean(self):
        """Validate that min <= max and ranges don't overlap"""
        if self.min_percentage > self.max_percentage:
            raise ValidationError('Minimum percentage cannot be greater than maximum percentage')

        # Check for overlapping ranges within the same grading system
        overlapping = GradeScale.objects.filter(
            grading_system=self.grading_system
        ).exclude(pk=self.pk).filter(
            models.Q(
                min_percentage__lte=self.max_percentage,
                max_percentage__gte=self.min_percentage
            )
        )

        if overlapping.exists():
            raise ValidationError(
                f'Grade range overlaps with existing grade: {overlapping.first()}'
            )

    class Meta:
        db_table = 'grade_scale'
        ordering = ['grading_system', 'order', '-min_percentage']
        verbose_name = 'Grade Scale'
        verbose_name_plural = 'Grade Scales'
        unique_together = ['grading_system', 'grade_label']
        indexes = [
            models.Index(fields=['grading_system', 'min_percentage', 'max_percentage']),
        ]
        constraints = [
            # Ensure min_percentage <= max_percentage
            models.CheckConstraint(
                check=models.Q(min_percentage__lte=models.F('max_percentage')),
                name='grade_scale_min_lte_max'
            ),
            # Ensure percentages are within 0-100 range
            models.CheckConstraint(
                check=models.Q(min_percentage__gte=0) & models.Q(min_percentage__lte=100),
                name='grade_scale_min_percentage_range'
            ),
            models.CheckConstraint(
                check=models.Q(max_percentage__gte=0) & models.Q(max_percentage__lte=100),
                name='grade_scale_max_percentage_range'
            ),
        ]


class AssessmentCategory(models.Model):
    """
    School-wide assessment categories (applies to all subjects).
    e.g., Class Score (30%), Examination (70%)
    """
    # Category types for programmatic identification
    CATEGORY_TYPES = [
        ('CLASS_SCORE', 'Class Score / Continuous Assessment'),
        ('EXAM', 'Examination / Final Exam'),
        ('OTHER', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100,
        help_text='Category name (e.g., Class Score, Examination)'
    )
    short_name = models.CharField(
        max_length=10,
        help_text='Short code (e.g., CA, EXAM)'
    )
    category_type = models.CharField(
        max_length=15,
        choices=CATEGORY_TYPES,
        default='OTHER',
        help_text='Type of category for grade calculation'
    )
    percentage = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Weight percentage for this category (0-100)'
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text='Display order (lower numbers appear first)'
    )
    # Advisory fields for assessment count guidance
    expected_assessments = models.PositiveSmallIntegerField(
        default=0,
        help_text='Recommended number of assessments per term (0 = no recommendation)'
    )
    min_assessments = models.PositiveSmallIntegerField(
        default=0,
        help_text='Minimum required assessments per term (0 = no minimum)'
    )
    max_assessments = models.PositiveSmallIntegerField(
        default=0,
        help_text='Maximum allowed assessments per term (0 = no maximum)'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.percentage}%)"

    def clean(self):
        """Validate that total percentages don't exceed 100%"""
        if self.percentage is None:
            return

        total = AssessmentCategory.objects.filter(
            is_active=True
        ).exclude(
            pk=self.pk
        ).aggregate(
            total=models.Sum('percentage')
        )['total'] or 0

        if self.is_active and total + self.percentage > 100:
            raise ValidationError(
                f'Total percentage cannot exceed 100%. Current: {total}%, Adding: {self.percentage}%'
            )

    def get_weight_per_assignment(self, subject, term):
        """
        Calculate the weight of each assignment in this category for a specific subject/term.
        Category weight is divided equally among all assignments.
        """
        assignment_count = Assignment.objects.filter(
            assessment_category=self,
            subject=subject,
            term=term
        ).count()

        if assignment_count == 0:
            return Decimal('0.0')
        return Decimal(str(self.percentage)) / Decimal(str(assignment_count))

    def get_assessment_count(self, subject, term):
        """Get the number of assessments for this category in a subject/term."""
        return Assignment.objects.filter(
            assessment_category=self,
            subject=subject,
            term=term
        ).count()

    def get_assessment_status(self, subject, term):
        """
        Check if the assessment count for a subject/term meets the advisory guidelines.

        Returns a dict with:
        - count: actual number of assessments
        - expected: recommended count (0 if none set)
        - min: minimum required (0 if none set)
        - max: maximum allowed (0 if none set)
        - status: 'ok', 'below_min', 'above_max', 'below_expected', 'above_expected'
        - message: human-readable status message
        """
        count = self.get_assessment_count(subject, term)

        result = {
            'count': count,
            'expected': self.expected_assessments,
            'min': self.min_assessments,
            'max': self.max_assessments,
            'status': 'ok',
            'message': '',
        }

        # Check minimum constraint (strict)
        if self.min_assessments > 0 and count < self.min_assessments:
            result['status'] = 'below_min'
            result['message'] = f'Requires at least {self.min_assessments} assessment(s), has {count}'
            return result

        # Check maximum constraint (strict)
        if self.max_assessments > 0 and count > self.max_assessments:
            result['status'] = 'above_max'
            result['message'] = f'Maximum {self.max_assessments} assessment(s) allowed, has {count}'
            return result

        # Check expected count (advisory, not strict)
        if self.expected_assessments > 0:
            if count < self.expected_assessments:
                result['status'] = 'below_expected'
                result['message'] = f'Expected {self.expected_assessments}, has {count}'
            elif count > self.expected_assessments:
                result['status'] = 'above_expected'
                result['message'] = f'Expected {self.expected_assessments}, has {count}'

        return result

    def validate_assessment_count(self, subject, term):
        """
        Validate that the assessment count meets minimum/maximum constraints.
        Raises ValidationError if constraints are violated.
        """
        status = self.get_assessment_status(subject, term)

        if status['status'] == 'below_min':
            raise ValidationError(status['message'])
        if status['status'] == 'above_max':
            raise ValidationError(status['message'])

    class Meta:
        db_table = 'assessment_category'
        ordering = ['order', 'name']
        verbose_name = 'Assessment Category'
        verbose_name_plural = 'Assessment Categories'
        unique_together = ['name']
        constraints = [
            # Ensure percentage is within 0-100 range
            models.CheckConstraint(
                check=models.Q(percentage__gte=0) & models.Q(percentage__lte=100),
                name='assessment_category_percentage_range'
            ),
        ]


class Assignment(models.Model):
    """
    Individual assignment within a category for a specific subject/term.
    e.g., Quiz 1, Mid-term Test, Final Exam
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment_category = models.ForeignKey(
        AssessmentCategory,
        on_delete=models.CASCADE,
        related_name='assignments',
        db_index=True
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='assignments',
        db_index=True
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='assignments',
        db_index=True
    )
    name = models.CharField(
        max_length=100,
        help_text='Assignment name (e.g., Quiz 1, Mid-term Test)'
    )
    points_possible = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Maximum points available for this assignment'
    )
    date = models.DateField(
        help_text='Date the assignment was administered'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Date/time the assignment was recorded in the system'
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.subject.name} - {self.assessment_category.short_name}: {self.name}"

    def get_weight(self):
        """Get this assignment's weight as a percentage of the final grade"""
        return self.assessment_category.get_weight_per_assignment(self.subject, self.term)

    def get_student_score(self, student):
        """Get a specific student's score for this assignment"""
        return self.scores.filter(student=student).first()

    class Meta:
        db_table = 'assignment'
        ordering = ['term', 'subject', 'assessment_category__order', 'name']
        verbose_name = 'Assignment'
        verbose_name_plural = 'Assignments'
        unique_together = ['assessment_category', 'subject', 'term', 'name']
        indexes = [
            models.Index(fields=['subject', 'term', 'assessment_category']),
        ]
        constraints = [
            # Ensure points_possible > 0
            models.CheckConstraint(
                check=models.Q(points_possible__gt=0),
                name='assignment_points_positive'
            ),
        ]


class Score(models.Model):
    """Student score for an individual assignment"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='scores',
        db_index=True
    )
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='scores',
        db_index=True
    )
    points = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Points earned on this assignment'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - {self.assignment.name}: {self.points}/{self.assignment.points_possible}"

    def clean(self):
        """Validate that points don't exceed points_possible"""
        if self.points > self.assignment.points_possible:
            raise ValidationError(
                f'Points ({self.points}) cannot exceed points possible ({self.assignment.points_possible})'
            )

    def get_percentage(self):
        """Get the percentage score for this assignment"""
        return round((Decimal(str(self.points)) / Decimal(str(self.assignment.points_possible))) * 100, 2)

    def get_contribution_to_final_grade(self):
        """Calculate how much this score contributes to the final grade"""
        percentage = Decimal(str(self.points)) / Decimal(str(self.assignment.points_possible))
        weight = self.assignment.get_weight()
        return round(percentage * weight, 2)

    class Meta:
        db_table = 'score'
        ordering = ['student', 'assignment']
        verbose_name = 'Score'
        verbose_name_plural = 'Scores'
        unique_together = ['student', 'assignment']
        indexes = [
            models.Index(fields=['student', 'assignment']),
        ]
        constraints = [
            # Ensure points >= 0
            models.CheckConstraint(
                check=models.Q(points__gte=0),
                name='score_points_non_negative'
            ),
        ]


class ScoreAuditLog(models.Model):
    """
    Audit log for score changes. Tracks who changed what and when.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ACTION_CHOICES = [
        ('CREATE', 'Created'),
        ('UPDATE', 'Updated'),
        ('DELETE', 'Deleted'),
    ]

    # The score being audited (null if deleted)
    score = models.ForeignKey(
        Score,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )

    # Store identifiers separately in case score is deleted
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='score_audit_logs'
    )
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='score_audit_logs'
    )

    # Who made the change
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='score_audit_logs'
    )

    # What changed
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    old_value = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Previous score value'
    )
    new_value = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='New score value'
    )

    # When
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional: extra context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.get_action_display()} score for {self.student} on {self.assignment.name} by {self.user}"

    class Meta:
        db_table = 'score_audit_log'
        ordering = ['-created_at']
        verbose_name = 'Score Audit Log'
        verbose_name_plural = 'Score Audit Logs'
        indexes = [
            models.Index(fields=['student', 'assignment']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['-created_at']),
        ]


class SubjectTermGrade(models.Model):
    """
    Aggregated term grade for a student in a subject.
    Computed from individual Scores.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='subject_grades',
        db_index=True
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='term_grades',
        db_index=True
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='subject_grades',
        db_index=True
    )

    # Score breakdown by category (computed)
    class_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Class work/CA total percentage (legacy, for standard 2-category system)'
    )
    exam_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Examination percentage (legacy, for standard 2-category system)'
    )
    # Dynamic category scores - supports any number of assessment categories
    # Format: {"category_id": {"score": 15.5, "short_name": "CA", "name": "Class Score"}, ...}
    category_scores = models.JSONField(
        default=dict,
        blank=True,
        help_text='Scores for each assessment category (supports multiple categories)'
    )
    total_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Total percentage (sum of all category scores)'
    )

    # Grade (looked up from GradeScale)
    grade = models.CharField(
        max_length=5,
        blank=True,
        help_text='Grade label (e.g., A1, B2)'
    )
    grade_remark = models.CharField(
        max_length=50,
        blank=True,
        help_text='Grade interpretation (e.g., Excellent)'
    )

    # Position in class for this subject
    position = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='Class rank for this subject'
    )

    teacher_remark = models.CharField(max_length=200, blank=True)

    # Pass/fail status (set from GradeScale.is_pass during grade calculation)
    is_passing = models.BooleanField(
        default=False,
        help_text='Whether this grade is a pass based on grading system'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - {self.subject.name} ({self.term}): {self.total_score}%"

    def calculate_scores(self):
        """Calculate scores from individual assignment scores.

        Populates:
        - category_scores: JSON with all category breakdowns
        - class_score: Sum of CLASS_SCORE type categories (legacy)
        - exam_score: Sum of EXAM type categories (legacy)
        - total_score: Sum of all categories
        """
        categories = AssessmentCategory.objects.filter(is_active=True).order_by('order')
        category_totals = {}
        category_scores_json = {}
        total = Decimal('0.0')
        class_score_total = Decimal('0.0')
        exam_score_total = Decimal('0.0')

        for category in categories:
            assignments = Assignment.objects.filter(
                assessment_category=category,
                subject=self.subject,
                term=self.term
            )

            if not assignments.exists():
                continue

            weight_per_assignment = category.get_weight_per_assignment(self.subject, self.term)
            category_total = Decimal('0.0')

            for assignment in assignments:
                score = Score.objects.filter(
                    student=self.student,
                    assignment=assignment
                ).first()

                if score:
                    score_pct = Decimal(str(score.points)) / Decimal(str(assignment.points_possible))
                    category_total += score_pct * weight_per_assignment

            rounded_total = round(category_total, 2)

            # Store in JSON format for dynamic category support
            category_scores_json[str(category.pk)] = {
                'score': float(rounded_total),
                'short_name': category.short_name,
                'name': category.name,
                'percentage': category.percentage,
                'category_type': category.category_type,
                'order': category.order,
            }

            # Store by short_name for backwards compatibility
            category_totals[category.short_name] = rounded_total
            total += category_total

            # Aggregate by category type for legacy fields
            if category.category_type == 'CLASS_SCORE':
                class_score_total += category_total
            elif category.category_type == 'EXAM':
                exam_score_total += category_total

        # Store dynamic category scores
        self.category_scores = category_scores_json

        # Store legacy fields (aggregated by category_type)
        self.class_score = round(class_score_total, 2)
        self.exam_score = round(exam_score_total, 2)
        self.total_score = round(total, 2)

        return category_totals

    def determine_grade(self, grading_system):
        """Look up grade from GradeScale based on total_score"""
        if self.total_score is None:
            self.is_passing = False
            return

        grade_scale = GradeScale.objects.filter(
            grading_system=grading_system,
            min_percentage__lte=self.total_score,
            max_percentage__gte=self.total_score
        ).first()

        if grade_scale:
            self.grade = grade_scale.grade_label
            self.grade_remark = grade_scale.interpretation
            self.is_passing = grade_scale.is_pass
        else:
            self.is_passing = False

    class Meta:
        db_table = 'subject_term_grade'
        ordering = ['term', 'subject', '-total_score']
        verbose_name = 'Subject Term Grade'
        verbose_name_plural = 'Subject Term Grades'
        unique_together = ['student', 'subject', 'term']
        indexes = [
            models.Index(fields=['student', 'term']),
            models.Index(fields=['subject', 'term', 'total_score']),
            models.Index(fields=['is_passing']),  # For filtering passing/failing grades
        ]


class TermReport(models.Model):
    """
    Overall term report for a student (report card summary).
    Aggregated from SubjectTermGrades.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='term_reports',
        db_index=True
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='term_reports',
        db_index=True
    )

    # Aggregated scores
    total_marks = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        help_text='Sum of all subject scores'
    )
    average = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='Average percentage across all subjects'
    )

    # Class position
    position = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='Overall class position'
    )
    out_of = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='Total students in class'
    )

    # Subject counts
    subjects_taken = models.PositiveSmallIntegerField(default=0)
    subjects_passed = models.PositiveSmallIntegerField(default=0)
    subjects_failed = models.PositiveSmallIntegerField(default=0)

    # Ghana SHS-specific: WASSCE aggregate and credits
    aggregate = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='WASSCE aggregate (sum of best 6 subject grades, lower is better)'
    )
    credits_count = models.PositiveSmallIntegerField(
        default=0,
        help_text='Number of subjects with credit passes (C6 or better)'
    )
    core_subjects_passed = models.PositiveSmallIntegerField(
        default=0,
        help_text='Number of core subjects passed'
    )
    core_subjects_total = models.PositiveSmallIntegerField(
        default=0,
        help_text='Total number of core subjects taken'
    )

    # Remarks
    class_teacher_remark = models.TextField(blank=True)
    head_teacher_remark = models.TextField(blank=True)

    # Conduct and Behavior Ratings
    CONDUCT_CHOICES = [
        ('A', 'Excellent'),
        ('B', 'Very Good'),
        ('C', 'Good'),
        ('D', 'Fair'),
        ('E', 'Poor'),
    ]
    RATING_CHOICES = [
        ('EXCELLENT', 'Excellent'),
        ('VERY_GOOD', 'Very Good'),
        ('GOOD', 'Good'),
        ('FAIR', 'Fair'),
        ('POOR', 'Poor'),
    ]

    conduct_rating = models.CharField(
        max_length=1,
        choices=CONDUCT_CHOICES,
        blank=True,
        help_text='Overall conduct grade (A-E)'
    )
    attitude_rating = models.CharField(
        max_length=10,
        choices=RATING_CHOICES,
        blank=True,
        help_text='Attitude to work'
    )
    interest_rating = models.CharField(
        max_length=10,
        choices=RATING_CHOICES,
        blank=True,
        help_text='Interest in school activities'
    )
    punctuality_rating = models.CharField(
        max_length=10,
        choices=RATING_CHOICES,
        blank=True,
        help_text='Punctuality record'
    )

    # Approval tracking
    class_teacher_signed = models.BooleanField(
        default=False,
        help_text='Class teacher has confirmed the remarks'
    )
    class_teacher_signed_at = models.DateTimeField(null=True, blank=True)
    head_teacher_approved = models.BooleanField(
        default=False,
        help_text='Head teacher has approved the report'
    )
    head_teacher_approved_at = models.DateTimeField(null=True, blank=True)

    # Attendance (optional, pulled from AttendanceRecord)
    attendance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    days_present = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='Number of days present in the term'
    )
    days_absent = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='Number of days absent in the term'
    )
    total_school_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='Total school days in the term'
    )

    # Promotion (for final term)
    promoted = models.BooleanField(
        null=True,
        blank=True,
        help_text='Promotion status (null = not final term)'
    )
    promoted_to = models.ForeignKey(
        'academics.Class',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='promoted_students',
        help_text='Class promoted to (if promoted)'
    )
    promotion_remarks = models.TextField(
        blank=True,
        help_text='Reasons for promotion decision'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - {self.term}: Position {self.position}/{self.out_of}"

    def calculate_aggregates(self, grading_system=None):
        """
        Recalculate all aggregates from SubjectTermGrades.
        Uses grading_system for pass/credit thresholds if provided.
        """
        subject_grades = SubjectTermGrade.objects.filter(
            student=self.student,
            term=self.term,
            total_score__isnull=False
        ).select_related('subject')

        if not subject_grades.exists():
            return

        total = sum(sg.total_score for sg in subject_grades)
        count = subject_grades.count()

        self.total_marks = total
        self.average = round(total / count, 2) if count > 0 else Decimal('0.0')
        self.subjects_taken = count

        # Determine pass threshold
        if grading_system:
            pass_mark = grading_system.pass_mark
            credit_mark = grading_system.credit_mark
        else:
            # Default Ghana standard: 50% pass, 50% credit
            pass_mark = Decimal('50.00')
            credit_mark = Decimal('50.00')

        # Count passed/failed using configurable threshold
        passed_grades = [sg for sg in subject_grades if sg.total_score >= pass_mark]
        self.subjects_passed = len(passed_grades)
        self.subjects_failed = count - self.subjects_passed

        # Count credits (C6 or better for WASSCE)
        self.credits_count = len([
            sg for sg in subject_grades if sg.total_score >= credit_mark
        ])

        # Core subjects breakdown
        core_grades = [sg for sg in subject_grades if sg.subject.is_core]
        self.core_subjects_total = len(core_grades)
        self.core_subjects_passed = len([
            sg for sg in core_grades if sg.total_score >= pass_mark
        ])

        # Calculate WASSCE aggregate if grading system provided
        if grading_system:
            aggregate, _ = grading_system.calculate_aggregate(subject_grades)
            self.aggregate = aggregate

    def calculate_attendance(self):
        """
        Calculate attendance from AttendanceRecord for the term.
        Links to the student's class and term dates.
        """
        from academics.models import AttendanceSession, AttendanceRecord

        # Get student's current class
        if not hasattr(self.student, 'current_class') or not self.student.current_class:
            return

        current_class = self.student.current_class

        # Get attendance sessions for this class within the term dates
        sessions = AttendanceSession.objects.filter(
            class_assigned=current_class,
            date__gte=self.term.start_date,
            date__lte=self.term.end_date
        )

        if not sessions.exists():
            return

        self.total_school_days = sessions.count()

        # Get student's attendance records
        records = AttendanceRecord.objects.filter(
            session__in=sessions,
            student=self.student
        )

        present_statuses = ['P', 'L']  # Present and Late count as present
        self.days_present = records.filter(status__in=present_statuses).count()
        self.days_absent = records.filter(status='A').count()

        if self.total_school_days > 0:
            self.attendance_percentage = round(
                (Decimal(str(self.days_present)) / Decimal(str(self.total_school_days))) * 100,
                2
            )

    def check_promotion(self, grading_system):
        """
        Check promotion eligibility and store result.
        Returns tuple of (is_eligible, reasons).
        """
        is_eligible, reasons = grading_system.check_promotion_eligibility(self)
        self.promotion_remarks = '; '.join(reasons) if reasons else 'Meets all requirements'
        return is_eligible, reasons

    def get_grade_summary(self):
        """
        Get a summary of grades by grade label for display.
        Returns dict like {'A1': 2, 'B2': 3, 'C4': 1, ...}
        """
        from collections import Counter
        subject_grades = SubjectTermGrade.objects.filter(
            student=self.student,
            term=self.term
        ).exclude(grade='')

        return dict(Counter(sg.grade for sg in subject_grades))

    class Meta:
        db_table = 'term_report'
        ordering = ['term', 'position']
        verbose_name = 'Term Report'
        verbose_name_plural = 'Term Reports'
        unique_together = ['student', 'term']
        indexes = [
            models.Index(fields=['term', 'average']),
            models.Index(fields=['term', 'aggregate']),
            models.Index(fields=['term', 'position']),  # For ranking queries
            models.Index(fields=['student', 'term']),  # For student report lookups
        ]


class RemarkTemplate(models.Model):
    """Pre-defined remark templates for teachers."""

    PERFORMANCE_CATEGORY = [
        ('EXCELLENT', 'Excellent (80%+)'),
        ('GOOD', 'Good (60-79%)'),
        ('AVERAGE', 'Average (50-59%)'),
        ('NEEDS_IMPROVEMENT', 'Needs Improvement (<50%)'),
        ('GENERAL', 'General'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(
        max_length=20,
        choices=PERFORMANCE_CATEGORY,
        default='GENERAL',
        help_text='Performance category this remark applies to'
    )
    content = models.TextField(
        help_text='Remark text. Use {student_name}, {average}, {position} as placeholders'
    )
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_category_display()}: {self.content[:50]}..."

    def render(self, context, escape_html=True):
        """
        Render template with context variables.

        Args:
            context: Dictionary of placeholder values
            escape_html: If True, escape HTML in values to prevent XSS (default: True)

        Returns:
            str: Rendered message with placeholders replaced
        """
        message = self.content
        for key, value in context.items():
            safe_value = html_escape(str(value)) if escape_html else str(value)
            message = message.replace(f'{{{key}}}', safe_value)
        return message

    class Meta:
        db_table = 'remark_template'
        ordering = ['category', 'order']
        verbose_name = 'Remark Template'
        verbose_name_plural = 'Remark Templates'
        indexes = [
            models.Index(fields=['is_active', 'category']),  # For filtering active templates
        ]


class ReportDistributionLog(models.Model):
    """Track report distribution to guardians via email and SMS."""

    DISTRIBUTION_TYPE = [
        ('EMAIL', 'Email with PDF'),
        ('SMS', 'SMS Summary'),
        ('BOTH', 'Email and SMS'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
        ('DELIVERED', 'Delivered'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    term_report = models.ForeignKey(
        TermReport,
        on_delete=models.CASCADE,
        related_name='distribution_logs'
    )
    distribution_type = models.CharField(
        max_length=10,
        choices=DISTRIBUTION_TYPE
    )

    # Email tracking
    email_status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    email_sent_to = models.EmailField(blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_error = models.TextField(blank=True)

    # SMS tracking
    sms_status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    sms_sent_to = models.CharField(max_length=20, blank=True)
    sms_sent_at = models.DateTimeField(null=True, blank=True)
    sms_error = models.TextField(blank=True)
    sms_message = models.ForeignKey(
        'communications.SMSMessage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='report_distributions'
    )

    # Who sent it
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='report_distributions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.term_report.student} - {self.get_distribution_type_display()} ({self.get_email_status_display()})"

    @property
    def is_successful(self):
        """Check if distribution was successful."""
        if self.distribution_type == 'EMAIL':
            return self.email_status in ['SENT', 'DELIVERED']
        elif self.distribution_type == 'SMS':
            return self.sms_status in ['SENT', 'DELIVERED']
        else:  # BOTH
            return (
                self.email_status in ['SENT', 'DELIVERED'] or
                self.sms_status in ['SENT', 'DELIVERED']
            )

    class Meta:
        db_table = 'report_distribution_log'
        ordering = ['-created_at']
        verbose_name = 'Report Distribution Log'
        verbose_name_plural = 'Report Distribution Logs'
        indexes = [
            models.Index(fields=['term_report', '-created_at']),
            models.Index(fields=['email_status']),
            models.Index(fields=['sms_status']),
        ]
