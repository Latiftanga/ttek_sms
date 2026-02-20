"""Base utilities, decorators, and helper functions for academics views."""
from core.utils import (  # noqa: F401
    is_school_admin, admin_required, htmx_render,
    is_teacher_or_admin, teacher_or_admin_required,
)
