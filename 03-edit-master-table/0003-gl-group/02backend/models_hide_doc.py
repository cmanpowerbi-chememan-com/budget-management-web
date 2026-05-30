"""Pydantic models for Hide Document Number payloads.

Composite PK 3 cols: (doc_num, fiscal_year, fiscal_month).
"""
from pydantic import BaseModel, Field


class HideDocumentNumberBase(BaseModel):
    doc_num: str = Field(..., min_length=10, max_length=10, pattern=r"^[0-9]{10}$")
    fiscal_year: int = Field(..., ge=2020, le=2099)
    fiscal_month: int = Field(..., ge=1, le=12)


class SaveRequest(HideDocumentNumberBase):
    pass


class DeleteRequest(HideDocumentNumberBase):
    pass
