"""Pydantic models for GL Group Master JSON payloads.

Validation rules sourced from spec.yml validation section + HTML
regex inputs.
"""
from pydantic import BaseModel, Field


class GlGroupMappingBase(BaseModel):
    """Core fields of a GL Group mapping row."""

    gl_code: str = Field(
        ...,
        min_length=1,
        max_length=20,
        pattern=r"^[0-9]+$",
        description="SAP G/L account code (digits only)",
    )


class SaveRequest(GlGroupMappingBase):
    """POST /save payload.

    The frontend sends either:
      - group_id (existing dim row)         OR
      - group_name (new, triggers create_on_save)
    Exactly one must be provided.
    """

    group_id:   str | None = Field(None, min_length=1, max_length=50)
    group_name: str | None = Field(None, min_length=1, max_length=200)
    is_edit_mode: bool = Field(
        False,
        description=(
            "True = UPDATE existing mapping (skip duplicate check). "
            "False = INSERT new (enforce Fail Fast)."
        ),
    )

    def model_post_init(self, __context) -> None:
        if not self.group_id and not self.group_name:
            raise ValueError("Either group_id or group_name must be provided")
        if self.group_id and self.group_name:
            raise ValueError(
                "Provide group_id OR group_name, not both"
            )


class DeleteRequest(BaseModel):
    """DELETE /delete payload."""

    gl_code: str = Field(..., min_length=1, max_length=20, pattern=r"^[0-9]+$")


class ListResponseItem(BaseModel):
    """One row in GET /list response."""

    gl_code:    str
    group_id:   str
    group_name: str  # joined from gl_group_dim for display
