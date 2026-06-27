"""Pydantic models for structured bulk-import results."""

from pydantic import BaseModel


class RowError(BaseModel):
    row_index: int
    field: str
    value: str
    rule: str


class ImportResult(BaseModel):
    total: int
    inserted: int
    skipped: int
    failed: list[RowError]
