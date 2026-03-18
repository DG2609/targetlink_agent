"""
Error classification cho retry strategy.

Chỉ chứa:
  - ErrorCategory: phân loại lỗi
  - classify_error(): xác định loại lỗi từ ValidationResult
  - EARLY_ESCALATE_AFTER: threshold escalate Agent 4 → Agent 5

Routing logic nằm ở pipeline/state_machine.py (RetryStateMachine).
"""

import re

from schemas.validation_schemas import ValidationResult, ValidationStatus


class ErrorCategory:
    """Phân loại lỗi để quyết định retry strategy."""
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    LOGIC_ERROR = "logic_error"
    PARTIAL_PASS = "partial_pass"
    TIMEOUT = "timeout"
    XPATH_ERROR = "xpath_error"
    UNKNOWN = "unknown"


def classify_error(result: ValidationResult) -> str:
    """Phân loại lỗi dựa trên stderr/status.

    Returns:
        ErrorCategory constant.
    """
    if result.status == ValidationStatus.PARTIAL_PASS:
        return ErrorCategory.PARTIAL_PASS

    if result.status == ValidationStatus.WRONG_RESULT:
        return ErrorCategory.LOGIC_ERROR

    stderr = (result.stderr or "").lower()

    if "timeout" in stderr:
        return ErrorCategory.TIMEOUT

    if any(kw in stderr for kw in ("syntaxerror", "indentationerror", "unexpected eof")):
        return ErrorCategory.SYNTAX_ERROR

    if any(kw in stderr for kw in ("modulenotfounderror", "importerror", "no module named")):
        return ErrorCategory.IMPORT_ERROR

    if re.search(r"xpath|lxml\.etree|xpatherror", stderr):
        return ErrorCategory.XPATH_ERROR

    return ErrorCategory.UNKNOWN


# Số lần retry Agent 4 tối đa trước khi escalate sang Agent 5, theo loại lỗi.
# Dùng bởi RetryStateMachine._route_code_error().
EARLY_ESCALATE_AFTER: dict[str, int] = {
    ErrorCategory.SYNTAX_ERROR: 1,     # Syntax sai → escalate sớm
    ErrorCategory.IMPORT_ERROR: 1,     # Import sai → cần approach mới
    ErrorCategory.TIMEOUT: 1,          # Timeout → code loop vô hạn
    ErrorCategory.XPATH_ERROR: 2,      # XPath sai → thử 2 lần rồi escalate
    ErrorCategory.LOGIC_ERROR: 3,      # Logic sai → dùng hết retry agent5
    ErrorCategory.PARTIAL_PASS: 0,     # Partial → skip agent4, đi thẳng agent5
    ErrorCategory.UNKNOWN: 3,          # Unknown → dùng hết retry mặc định
}
