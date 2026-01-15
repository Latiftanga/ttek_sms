# Teacher CRUD views
from .teachers import (
    index,
    teacher_create,
    teacher_edit,
    teacher_detail,
    teacher_detail_pdf,
    teacher_delete,
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
    send_invitation,
    resend_invitation,
    cancel_invitation,
    accept_invitation,
)

# Bulk import views
from .bulk_import import (
    bulk_import,
    bulk_import_confirm,
    bulk_import_template,
)

__all__ = [
    # Teachers
    'index',
    'teacher_create',
    'teacher_edit',
    'teacher_detail',
    'teacher_detail_pdf',
    'teacher_delete',
    # Dashboard
    'profile',
    'dashboard',
    'schedule',
    'teacher_schedule',
    # Accounts
    'create_account',
    'deactivate_account',
    'reset_password',
    'send_invitation',
    'resend_invitation',
    'cancel_invitation',
    'accept_invitation',
    # Bulk import
    'bulk_import',
    'bulk_import_confirm',
    'bulk_import_template',
]
