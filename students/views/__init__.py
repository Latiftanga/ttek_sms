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

# Guardian account views
from .accounts import (
    guardian_detail,
    send_invitation as guardian_send_invitation,
    resend_invitation as guardian_resend_invitation,
    cancel_invitation as guardian_cancel_invitation,
    accept_invitation as guardian_accept_invitation,
    deactivate_account as guardian_deactivate_account,
    activate_account as guardian_activate_account,
)

# Bulk import/export views
from .bulk_import import (
    bulk_import,
    bulk_import_confirm,
    bulk_import_template,
    bulk_export,
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
    house_assign_master,
    house_remove_master,
)

# Exeat views
from .exeat import (
    exeat_index,
    exeat_create,
    exeat_detail,
    exeat_approve,
    exeat_reject,
    exeat_depart,
    exeat_return,
    exeat_student_search,
    exeat_report,
    exeat_report_pdf,
    exeat_report_excel,
    housemaster_index,
    housemaster_assign,
    housemaster_remove,
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
    'guardian_detail',
    'guardian_send_invitation',
    'guardian_resend_invitation',
    'guardian_cancel_invitation',
    'guardian_accept_invitation',
    'guardian_deactivate_account',
    'guardian_activate_account',
    # Bulk import/export
    'bulk_import',
    'bulk_import_confirm',
    'bulk_import_template',
    'bulk_export',
    # Promotion
    'promotion',
    'promotion_process',
    # Houses
    'house_index',
    'house_create',
    'house_edit',
    'house_delete',
    'house_assign_master',
    'house_remove_master',
    # Exeats
    'exeat_index',
    'exeat_create',
    'exeat_detail',
    'exeat_approve',
    'exeat_reject',
    'exeat_depart',
    'exeat_return',
    'exeat_student_search',
    'exeat_report',
    'exeat_report_pdf',
    'exeat_report_excel',
    'housemaster_index',
    'housemaster_assign',
    'housemaster_remove',
]
