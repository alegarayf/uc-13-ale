"""Cycle-1 F3: Elder Care employment under-classification (G1 ≥2 employee rows)."""

from __future__ import annotations

import inspect

from agents.workstreams.legal_contracts_agent import (
    LegalContractsAgent,
    _ensure_employee_class_rows,
    _eq_str,
    _reconcile_employee_class_from_instrument,
)

# Live uc13_ale.analysis.legal Elder Care row created_at 2026-09-01 16:33:09 —
# 4 rows, only one agreement_class=employee. This is the miss fixture.
_SEPT1_ELDER_CARE_EMPLOYMENT_MISS = [
    {
        "person_or_role": "Employee (unnamed template)",
        "agreement_class": "employee",
        "source_doc": "Non-Compete-Non Solicitation Agreement Template.docx",
        "source_location": "Document body",
        "raw_quote": (
            "THIS AGREEMENT is made this ____ day of ________________, by and "
            "between Unicity Healthcare (hereinafter referred to as \"Employer\") "
            "and __________________ (hereinafter referred to as \"Employee\")."
        ),
    },
    {
        "person_or_role": "Contractor (unnamed, Laguna Contract Agreement)",
        "agreement_class": "contractor",
        "source_doc": "Laguna Contract Agreement 2025.pdf",
        "source_location": "Section 3. RELATIONSHIP OF THE PARTIES, §3.1",
        "raw_quote": (
            "Contractor's relationship with Client will be that of an independent "
            "contractor acting as a service provider to Client, and not that of "
            "an employee, worker, agent or partner of Client."
        ),
    },
    {
        "person_or_role": "Stockholder (unnamed, Stock Transfer Agreement)",
        "agreement_class": "founder_key",
        "source_doc": "Stock Transfer & Amend to Bylaws_LG-EM_10.25.21.pdf",
        "source_location": "Section 2. Restrictions on Transfer., §2(a)",
        "raw_quote": (
            "No Stockholder of the Corporation may sell, assign, transfer, pledge, "
            "encumber, grant an economic or participation interest in, or in any "
            "manner dispose of any share of Common Stock."
        ),
    },
    {
        "person_or_role": "Kate Marks",
        "agreement_class": "founder_key",
        "source_doc": "Kate Marks Restricted Stock.pdf",
        "source_location": "Section 5) Issuance of Stock., §5(a)",
        "raw_quote": (
            "Prior to the issuance of Stock to any person, such person shall "
            "execute and deliver to the Company a joinder to the most recent "
            "version of the Company's Shareholders Agreement."
        ),
    },
]


def _employee_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if _eq_str(row.get("agreement_class"), "employee")]


def test_sept1_elder_care_fixture_yields_at_least_two_employee_rows():
    """Falsifier: employee-class extraction must not stay at a single employee
    row on the Sept 1 Elder Care miss fixture (G1 employment pass needs ≥2).

    Restricted stock is an employee instrument (golden checklist) as well as
    founder_key — dual-class it. Do not reclassify the Laguna IC or the
    stock-transfer / bylaws row.
    """
    before = _employee_rows(_SEPT1_ELDER_CARE_EMPLOYMENT_MISS)
    assert len(before) == 1

    merged = {"employment_register": [dict(row) for row in _SEPT1_ELDER_CARE_EMPLOYMENT_MISS]}
    _reconcile_employee_class_from_instrument(merged)
    rows = merged["employment_register"]
    employees = _employee_rows(rows)
    assert len(employees) >= 2

    kate_classes = {
        row["agreement_class"]
        for row in rows
        if row.get("person_or_role") == "Kate Marks"
    }
    assert "founder_key" in kate_classes
    assert "employee" in kate_classes

    laguna = [
        row
        for row in rows
        if "Laguna" in str(row.get("source_doc") or "")
    ]
    assert len(laguna) == 1
    assert laguna[0]["agreement_class"] == "contractor"

    stock_transfer = [
        row
        for row in rows
        if "Stock Transfer" in str(row.get("source_doc") or "")
    ]
    assert len(stock_transfer) == 1
    assert stock_transfer[0]["agreement_class"] == "founder_key"


def test_ensure_employee_class_rows_idempotent_on_miss_fixture():
    once = _ensure_employee_class_rows(
        [dict(row) for row in _SEPT1_ELDER_CARE_EMPLOYMENT_MISS]
    )
    twice = _ensure_employee_class_rows(once)
    assert len(_employee_rows(once)) == len(_employee_rows(twice))
    assert len(twice) == len(once)


def test_handbook_misclassified_as_contractor_gets_employee_sibling():
    rows = _ensure_employee_class_rows(
        [
            {
                "person_or_role": "All employees (at-will)",
                "agreement_class": "contractor",
                "source_doc": "Elder Care Homecare - Unicity Handbook 09.2024.docx",
            }
        ]
    )
    assert len(_employee_rows(rows)) == 1
    assert any(_eq_str(row.get("agreement_class"), "contractor") for row in rows)


def test_run_wires_employee_class_reconcile_after_t4c():
    body = inspect.getsource(LegalContractsAgent.run)
    t4c_pos = body.index("_reconcile_t4c_from_nested_fields(merged)")
    emp_pos = body.index("_reconcile_employee_class_from_instrument(merged)")
    rollup_pos = body.index("_build_coc_consent_list(")
    assert t4c_pos < emp_pos < rollup_pos
