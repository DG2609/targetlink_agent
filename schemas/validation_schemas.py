"""
Schemas cho kết quả validation.
  - TestCase: 1 test case (model + expected result)
  - ValidationStatus: enum trạng thái
  - ValidationResult: output của Agent 3 (Validator)
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class TestCase(BaseModel):
    """1 test case cho validation: model .slx + expected result.

    Example:
        >>> tc = TestCase(
        ...     model_path="data/model4_CcodeGeneration.slx",
        ...     expected_total_blocks=19, expected_pass=18, expected_fail=1,
        ... )
    """

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "model_path": "data/model4_CcodeGeneration.slx",
                "expected_total_blocks": 19,
                "expected_pass": 18,
                "expected_fail": 1,
            },
        ]
    })

    model_path: str = Field(
        description="Đường dẫn tới file .slx test model",
        examples=["data/model4_CcodeGeneration.slx"],
    )
    expected_total_blocks: int = Field(
        description="Tổng số blocks expected",
        examples=[19, 2],
    )
    expected_pass: int = Field(
        description="Số blocks pass expected",
        examples=[18, 2],
    )
    expected_fail: int = Field(
        description="Số blocks fail expected",
        examples=[1, 0],
    )


class ValidationStatus(str, Enum):
    """Trạng thái validation — quyết định agent tiếp theo.

    Luồng routing:
      PASS             → DONE (dừng)
      CODE_ERROR       → Agent 4 (Bug Fixer) hoặc Agent 5 (escalation)
      WRONG_RESULT     → Agent 5 (Inspector)
      PARTIAL_PASS     → Agent 5 (Inspector), skip Agent 4
      SCHEMA_ERROR     → DONE (dừng, lỗi pipeline)
      FAILED_*         → DONE (dừng, hết retry)
    """
    PASS = "PASS"
    PARTIAL_PASS = "PARTIAL_PASS"
    CODE_ERROR = "CODE_ERROR"
    WRONG_RESULT = "WRONG_RESULT"
    FAILED_CODE_ERROR = "FAILED_CODE_ERROR"
    FAILED_WRONG_RESULT = "FAILED_WRONG_RESULT"
    FAILED_PARTIAL_PASS = "FAILED_PARTIAL_PASS"
    SCHEMA_ERROR = "SCHEMA_ERROR"


class ValidationResult(BaseModel):
    """Output của Agent 3 — quyết định pipeline đi tiếp hay retry.

    Example — PASS:
        >>> r = ValidationResult(
        ...     rule_id="R001", status=ValidationStatus.PASS,
        ...     test_cases_passed=1, test_cases_total=1,
        ...     code_file_path="generated_checks/check_rule_R001.py",
        ... )

    Example — CODE_ERROR:
        >>> r = ValidationResult(
        ...     rule_id="R001", status=ValidationStatus.CODE_ERROR,
        ...     stderr="AttributeError: 'NoneType' object has no attribute 'text'",
        ...     failed_test_case="data/model4_CcodeGeneration.slx",
        ...     test_cases_passed=0, test_cases_total=1,
        ...     code_file_path="generated_checks/check_rule_R001.py",
        ... )

    Example — WRONG_RESULT:
        >>> r = ValidationResult(
        ...     rule_id="R001", status=ValidationStatus.WRONG_RESULT,
        ...     actual_result={"total_blocks": 5, "pass_count": 5, "fail_count": 0},
        ...     expected_result={"total_blocks": 19, "pass": 18, "fail": 1},
        ...     failed_test_case="data/model4_CcodeGeneration.slx",
        ...     test_cases_passed=0, test_cases_total=1,
        ...     code_file_path="generated_checks/check_rule_R001.py",
        ... )
    """

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "rule_id": "R001",
                "status": "PASS",
                "test_cases_passed": 1,
                "test_cases_total": 1,
                "code_file_path": "generated_checks/check_rule_R001.py",
            },
            {
                "rule_id": "R001",
                "status": "WRONG_RESULT",
                "actual_result": {"total_blocks": 5, "pass_count": 5, "fail_count": 0},
                "expected_result": {"total_blocks": 19, "pass": 18, "fail": 1},
                "failed_test_case": "data/model4_CcodeGeneration.slx",
                "test_cases_passed": 0,
                "test_cases_total": 1,
                "code_file_path": "generated_checks/check_rule_R001.py",
            },
        ]
    })

    rule_id: str = Field(examples=["R001", "R002"])
    status: ValidationStatus
    stdout: Optional[str] = Field(default=None, description="Stdout từ subprocess (khi fail)")
    stderr: Optional[str] = Field(
        default=None,
        description="Stderr từ subprocess (traceback khi crash)",
        examples=[
            None,
            "Traceback (most recent call last):\n  File \"check_rule_R001.py\", line 32\n"
            "AttributeError: 'NoneType' object has no attribute 'text'",
        ],
    )
    actual_result: Optional[dict] = Field(
        default=None,
        description="Kết quả thực tế {total_blocks, pass_count, fail_count}",
        examples=[None, {"total_blocks": 5, "pass_count": 5, "fail_count": 0}],
    )
    expected_result: Optional[dict] = Field(
        default=None,
        description="Kết quả mong đợi {total_blocks, pass, fail}",
        examples=[None, {"total_blocks": 19, "pass": 18, "fail": 1}],
    )
    failed_test_case: Optional[str] = Field(
        default=None,
        description="model_path của test case bị fail đầu tiên",
        examples=[None, "data/model4_CcodeGeneration.slx"],
    )
    test_cases_passed: int = Field(default=0, ge=0, examples=[0, 1])
    test_cases_total: int = Field(default=0, ge=0, examples=[1, 2])
    code_file_path: str = Field(
        default="",
        examples=["generated_checks/check_rule_R001.py"],
    )
    actual_details: Optional[dict] = Field(
        default=None,
        description=(
            "Chi tiết pass/fail blocks từ stdout (nếu có). "
            "Giúp Agent 5 biết CHÍNH XÁC blocks nào fail mà không cần re-discover"
        ),
        examples=[None, {
            "pass_block_names": ["Gain1", "Gain2"],
            "fail_block_names": ["Gain3"],
        }],
    )
