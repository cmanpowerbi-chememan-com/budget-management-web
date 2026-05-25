"""Pydantic models for Hide Document Number JSON payloads.

Composite PK 3 cols: (doc_num, fiscal_year, fiscal_month).
Range validation mirrors HTML input min/max.
"""
from pydantic import BaseModel, Field


class HideDocumentNumberBase(BaseModel):
    """Core fields of a Hide Document Number row.

    All three columns are PK — the triple must be unique.
    Year/month stored separately for filterability (not "YYYY-MM").
    """

    doc_num: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="SAP Document Number (selected from sap_document_number_ref)",
    )

    fiscal_year: int = Field(
        ...,
        ge=2020,
        le=2099,
        description="Fiscal year (matches HTML input min=2020 max=2099)",
    )

    fiscal_month: int = Field(
        ...,
        ge=1,
        le=12,
        description="Fiscal month 1-12 (matches HTML dropdown)",
    )


class SaveRequest(HideDocumentNumberBase):
    """POST /save payload.

    Junction-like table — no non-PK columns.
    is_edit_mode reserved for API consistency.
    """

    is_edit_mode: bool = Field(
        False,
        description=(
            "Reserved for API consistency. "
            "Exclusion rule table has no non-PK columns to update."
        ),
    )


class DeleteRequest(HideDocumentNumberBase):
    """DELETE /delete payload — all 3 PK columns required."""
    pass


class ListResponseItem(HideDocumentNumberBase):
    """One row in GET /list response.

    `period` is a computed field for display only (YYYY-MM string).
    Not stored in DB — derived from fiscal_year + fiscal_month.
    """
    doc_name: str = ""    # joined from sap_document_number_ref
    period:   str = ""    # computed "YYYY-MM" for frontend display
