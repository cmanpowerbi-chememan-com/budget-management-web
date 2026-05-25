"""Pydantic models for Orgcode-CostCenter Master JSON payloads.

Composite PK: (cost_center, orgcode).
Both columns required in every CRUD operation.
"""
from pydantic import BaseModel, Field, field_validator


class OrgcodeCostcenterBase(BaseModel):
    """Core fields of an Orgcode-CostCenter mapping row.
    
    Both columns are PK — pair must be unique.
    """

    cost_center: str = Field(
        ...,
        min_length=1,
        max_length=20,
        pattern=r"^[0-9A-Z]+$",
        description="Cost Center code (uppercase alphanumeric, matches frontend regex)",
    )

    orgcode: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="SAP Orgcode (selected from cfg_master.sap_orgcode_ref)",
    )

    @field_validator("cost_center", mode="before")
    @classmethod
    def upper_cost_center(cls, v):
        """Match HTML auto_transform: upper — convert before regex check."""
        if isinstance(v, str):
            return v.upper().strip()
        return v


class SaveRequest(OrgcodeCostcenterBase):
    """POST /save payload.

    Junction table has no non-PK columns. is_edit_mode is included
    for API consistency with other entities but always behaves as
    "INSERT new" — there is nothing to UPDATE.
    """

    is_edit_mode: bool = Field(
        False,
        description=(
            "Reserved for API consistency. "
            "Junction table has no non-PK columns to update."
        ),
    )


class DeleteRequest(OrgcodeCostcenterBase):
    """DELETE /delete payload — both PK columns required."""
    pass


class ListResponseItem(OrgcodeCostcenterBase):
    """One row in GET /list response."""
    orgcode_name: str = ""  # joined from sap_orgcode_ref for display
