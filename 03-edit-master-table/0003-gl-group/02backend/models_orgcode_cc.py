"""Pydantic models for Orgcode-CostCenter mapping payloads."""
from pydantic import BaseModel, Field, field_validator


class OrgcodeCostcenterBase(BaseModel):
    cost_center: str = Field(..., min_length=1, max_length=20, pattern=r"^[0-9A-Z]+$")
    orgcode: str = Field(..., min_length=1, max_length=20)

    @field_validator("cost_center", mode="before")
    @classmethod
    def upper_cost_center(cls, v):
        return v.upper().strip() if isinstance(v, str) else v


class SaveRequest(OrgcodeCostcenterBase):
    is_edit_mode: bool = False


class DeleteRequest(OrgcodeCostcenterBase):
    pass
