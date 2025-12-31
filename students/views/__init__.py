# Student views
from .students import (
    index,
    student_create,
    student_edit,
    student_delete,
    student_detail,
)

# Guardian views
from .guardians import (
    guardian_index,
    guardian_create,
    guardian_edit,
    guardian_delete,
    guardian_search,
)

# Bulk import views
from .bulk_import import (
    bulk_import,
    bulk_import_confirm,
    bulk_import_template,
)

# Promotion views
from .promotion import (
    promotion,
    promotion_process,
)

__all__ = [
    # Students
    'index',
    'student_create',
    'student_edit',
    'student_delete',
    'student_detail',
    # Guardians
    'guardian_index',
    'guardian_create',
    'guardian_edit',
    'guardian_delete',
    'guardian_search',
    # Bulk import
    'bulk_import',
    'bulk_import_confirm',
    'bulk_import_template',
    # Promotion
    'promotion',
    'promotion_process',
]
