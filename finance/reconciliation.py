"""
Matching engine for bank statement reconciliation.

Takes parsed rows and attempts to match each credit row to an existing invoice.
"""

import re
import logging
from decimal import Decimal

from .models import BankStatementRow, Invoice, Payment

logger = logging.getLogger(__name__)

# Regex for invoice numbers like INV-2026-00012
_INV_RE = re.compile(r"INV-\d{4}-\d{5}")

# Broad regex for admission-number-like tokens (alphanumeric, 4–20 chars)
_ADM_RE = re.compile(r"\b([A-Za-z0-9/-]{4,20})\b")


def match_rows_to_invoices(parsed_rows, reconciliation):
    """
    Match a list of ParsedRow objects to invoices and bulk-create
    BankStatementRow records under the given BankReconciliation.

    Returns the list of created BankStatementRow instances.
    """
    from students.models import Student

    # ---- Pre-fetch lookups ----

    payable_statuses = {"ISSUED", "PARTIALLY_PAID", "OVERDUE"}

    # {invoice_number: invoice}
    invoice_map = {
        inv.invoice_number: inv
        for inv in Invoice.objects.filter(status__in=payable_statuses).select_related(
            "student"
        )
    }

    # {admission_number: invoice} — student's most recent unpaid invoice
    adm_invoice_map = {}
    students_with_invoices = (
        Student.objects.filter(
            invoices__status__in=payable_statuses,
            status="active",
        )
        .values_list("admission_number", flat=True)
        .distinct()
    )
    for adm in students_with_invoices:
        inv = (
            Invoice.objects.filter(
                student__admission_number=adm, status__in=payable_statuses
            )
            .order_by("-created_at")
            .first()
        )
        if inv:
            adm_invoice_map[adm.upper()] = inv

    # Existing payment references for dedup
    existing_refs = set(
        Payment.objects.filter(status="COMPLETED")
        .exclude(reference="")
        .values_list("reference", flat=True)
    )

    # ---- Match each row ----

    rows_to_create = []

    for parsed in parsed_rows:
        row = BankStatementRow(
            reconciliation=reconciliation,
            row_number=parsed.row_number,
            transaction_date=parsed.transaction_date,
            description=parsed.description,
            reference=parsed.reference,
            credit_amount=parsed.credit_amount,
            debit_amount=parsed.debit_amount,
        )

        # Skip debit rows (no credit)
        if parsed.credit_amount <= Decimal("0"):
            row.match_status = "SKIPPED"
            row.match_method = "debit_row"
            rows_to_create.append(row)
            continue

        combined_text = f"{parsed.description} {parsed.reference}"

        # Dedup: check if reference already used in a completed payment
        ref_for_dedup = parsed.reference.strip()
        if ref_for_dedup and ref_for_dedup in existing_refs:
            row.match_status = "DUPLICATE"
            row.match_method = "reference_exists"
            rows_to_create.append(row)
            continue

        # Primary match: invoice number in text
        inv_match = _INV_RE.search(combined_text)
        if inv_match:
            inv_num = inv_match.group(0)
            invoice = invoice_map.get(inv_num)
            if invoice:
                row.match_status = "MATCHED"
                row.matched_invoice = invoice
                row.match_method = "invoice_number"
                row.match_confidence = "high"
                rows_to_create.append(row)
                continue

        # Secondary match: admission number in text
        matched_via_adm = False
        for token_match in _ADM_RE.finditer(combined_text):
            token = token_match.group(1).upper()
            invoice = adm_invoice_map.get(token)
            if invoice:
                row.match_status = "MATCHED"
                row.matched_invoice = invoice
                row.match_method = "admission_number"
                row.match_confidence = "medium"
                matched_via_adm = True
                break

        if not matched_via_adm:
            row.match_status = "UNMATCHED"

        rows_to_create.append(row)

    # Bulk create
    created = BankStatementRow.objects.bulk_create(rows_to_create)
    logger.info(
        "Reconciliation %s: %d rows created (%d matched)",
        reconciliation.pk,
        len(created),
        sum(1 for r in created if r.match_status == "MATCHED"),
    )
    return created
