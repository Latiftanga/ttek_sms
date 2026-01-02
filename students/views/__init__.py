# Student views
from .students import (
    index,
    student_create,
    student_edit,
    student_delete,
    student_detail,
    student_detail_pdf,
    student_create_account,
    student_add_guardian,
    student_remove_guardian,
    student_set_primary_guardian,
    student_update_guardian_relationship,
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

# House views
from .houses import (
    house_index,
    house_create,
    house_edit,
    house_delete,
)

__all__ = [
    # Students
    'index',
    'student_create',
    'student_edit',
    'student_delete',
    'student_detail',
    'student_detail_pdf',
    'student_create_account',
    'student_add_guardian',
    'student_remove_guardian',
    'student_set_primary_guardian',
    'student_update_guardian_relationship',
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
    # Houses
    'house_index',
    'house_create',
    'house_edit',
    'house_delete',
]
