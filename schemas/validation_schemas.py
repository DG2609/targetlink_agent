"""
Schemas cho kết quả validation.
  - TestCase: 1 test case (model + expected result)
  - ValidationStatus: enum trạng thái
  - ValidationResult: output của Agent 3 (Validator)
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TestCase(BaseModel):
    """1 test case cho validation: model .slx + expected result."""
    model_path: str = Field(description="Đường dẫn tới file .slx test model")
    expected_total_blocks: int = Field(description="Tổng số blocks expected")
    expected_pass: int = Field(description="Số blocks pass expected")
    expected_fail: int = Field(description="Số blocks fail expected")


class ValidationStatus(str, Enum):
    PASS = "PASS"
    PARTIAL_PASS = "PARTIAL_PASS"
    CODE_ERROR = "CODE_ERROR"
    WRONG_RESULT = "WRONG_RESULT"
    FAILED_CODE_ERROR = "FAILED_CODE_ERROR"
    FAILED_WRONG_RESULT = "FAILED_WRONG_RESULT"
    FAILED_PARTIAL_PASS = "FAILED_PARTIAL_PASS"
    SCHEMA_ERROR = "SCHEMA_ERROR"


class ValidationResult(BaseModel):
    """Output của Agent 3 — quyết định pipeline đi tiếp hay retry."""
    rule_id: str
    status: ValidationStatus
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    actual_result: Optional[dict] = None
    expected_result: Optional[dict] = None
    failed_test_case: Optional[str] = Field(default=None, description="model_path của test case bị fail")
    test_cases_passed: int = Field(default=0, ge=0)
    test_cases_total: int = Field(default=0, ge=0)
    code_file_path: str = ""
