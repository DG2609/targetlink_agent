"""
Schemas cho kết quả validation.
  - ValidationStatus: enum trạng thái
  - ValidationResult: output của Agent 3 (Validator)
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    PASS = "PASS"
    CODE_ERROR = "CODE_ERROR"
    WRONG_RESULT = "WRONG_RESULT"
    FAILED_CODE_ERROR = "FAILED_CODE_ERROR"
    FAILED_WRONG_RESULT = "FAILED_WRONG_RESULT"
    SCHEMA_ERROR = "SCHEMA_ERROR"


class ValidationResult(BaseModel):
    """Output của Agent 3 — quyết định pipeline đi tiếp hay retry."""
    rule_id: str
    status: ValidationStatus
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    actual_result: Optional[dict] = None
    expected_result: Optional[dict] = None
    retry_count: int = Field(default=0, ge=0)
    code_file_path: str = ""
