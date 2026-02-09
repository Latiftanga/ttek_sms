# Teacher CRUD views
from .teachers import (
    index,
    teacher_create,
    teacher_edit,
    teacher_detail,
    teacher_detail_pdf,
    teacher_delete,
    assign_lesson,
    unassign_lesson,
)

# Teacher dashboard/portal views
from .dashboard import (
    profile,
    dashboard,
    schedule,
    teacher_schedule,
)

# Account management views
from .accounts import (
    create_account,
    deactivate_account,
    reset_password,
    toggle_school_admin,
    send_invitation,
    resend_invitation,
    cancel_invitation,
    accept_invitation,
)

# Bulk import/export views
from .bulk_import import (
    bulk_import,
    bulk_import_confirm,
    bulk_import_template,
    bulk_export,
)

# Analytics views
from .analytics import (
    my_workload,
    school_workload_overview,
)

# Promotion views
from .promotions import (
    promotion_list,
    promotion_create,
    promotion_edit,
    promotion_delete,
)

# Qualification views
from .qualifications import (
    qualification_list,
    qualification_create,
    qualification_edit,
    qualification_delete,
)

__all__ = [
    # Teachers
    'index',
    'teacher_create',
    'teacher_edit',
    'teacher_detail',
    'teacher_detail_pdf',
    'teacher_delete',
    'assign_lesson',
    'unassign_lesson',
    # Dashboard
    'profile',
    'dashboard',
    'schedule',
    'teacher_schedule',
    # Accounts
    'create_account',
    'deactivate_account',
    'reset_password',
    'toggle_school_admin',
    'send_invitation',
    'resend_invitation',
    'cancel_invitation',
    'accept_invitation',
    # Bulk import/export
    'bulk_import',
    'bulk_import_confirm',
    'bulk_import_template',
    'bulk_export',
    # Analytics
    'my_workload',
    'school_workload_overview',
    # Promotions
    'promotion_list',
    'promotion_create',
    'promotion_edit',
    'promotion_delete',
    # Qualifications
    'qualification_list',
    'qualification_create',
    'qualification_edit',
    'qualification_delete',
]
