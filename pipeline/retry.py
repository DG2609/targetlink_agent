"""
Quản lý retry và escalation policy.
Agent 4 xử lý CODE_ERROR, Agent 5 xử lý WRONG_RESULT — mỗi cái có max_retries RIÊNG.
Theo dõi error history để agent biết những gì đã thử, tránh lặp lại approach cũ.

Adaptive retry: phân loại lỗi → quyết định escalation sớm hay tiếp tục retry.
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
    """Phân loại lỗi dựa trên stderr/status để chọn retry strategy.

    Returns:
        ErrorCategory constant.
    """
    if result.status == ValidationStatus.PARTIAL_PASS:
        return ErrorCategory.PARTIAL_PASS

    if result.status in (ValidationStatus.WRONG_RESULT,):
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


# Số lần retry tối đa trước khi escalate, theo loại lỗi
_EARLY_ESCALATE_AFTER: dict[str, int] = {
    ErrorCategory.SYNTAX_ERROR: 1,     # Syntax sai → agent4 khó fix lặp → escalate sớm
    ErrorCategory.IMPORT_ERROR: 1,     # Import sai → cần approach mới
    ErrorCategory.TIMEOUT: 1,          # Timeout → code có thể loop vô hạn
    ErrorCategory.XPATH_ERROR: 2,      # XPath sai → agent4 thử 2 lần rồi escalate
    ErrorCategory.LOGIC_ERROR: 3,      # Logic sai → dùng hết retry agent5
    ErrorCategory.PARTIAL_PASS: 0,     # Partial → skip agent4, đi thẳng agent5
    ErrorCategory.UNKNOWN: 3,          # Unknown → dùng hết retry mặc định
}


class RetryManager:
    """Theo dõi số lần retry, error history, và quyết định có nên tiếp tục không.

    Adaptive: phân loại lỗi và escalate sớm nếu retry cùng agent không hiệu quả.
    """

    def __init__(self, max_retries_agent4: int = 3, max_retries_agent5: int = 3):
        self.max_retries = {
            "agent4": max_retries_agent4,
            "agent5": max_retries_agent5,
        }
        self.counts: dict[str, int] = {"agent4": 0, "agent5": 0}
        self._trace: list[dict] = []
        self._error_history: list[str] = []
        self._error_categories: list[str] = []

    def increment(self, agent_name: str) -> None:
        self.counts[agent_name] = self.counts.get(agent_name, 0) + 1
        self._trace.append({
            "agent": agent_name,
            "attempt": self.counts[agent_name],
        })

    def add_error(self, error_summary: str, category: str = "") -> None:
        """Ghi nhận lỗi để truyền cho agent ở lần retry sau."""
        self._error_history.append(error_summary)
        if category:
            self._error_categories.append(category)

    def get_error_history(self) -> list[str]:
        return list(self._error_history)

    def get_last_error_category(self) -> str:
        """Trả về category lỗi gần nhất."""
        return self._error_categories[-1] if self._error_categories else ErrorCategory.UNKNOWN

    def should_escalate(self, result: ValidationResult) -> bool:
        """Quyết định có nên escalate từ agent4 → agent5 không.

        Adaptive: dựa vào loại lỗi để escalate sớm hơn default.
        """
        if result.status != ValidationStatus.CODE_ERROR:
            return False

        category = classify_error(result)
        escalate_threshold = _EARLY_ESCALATE_AFTER.get(category, self.max_retries["agent4"])

        # Escalate nếu: đã retry đủ threshold HOẶC hết retry agent4
        should = (
            self.counts["agent4"] >= min(escalate_threshold, self.max_retries["agent4"])
            and self.counts["agent5"] < self.max_retries["agent5"]
        )
        return should

    def should_skip_agent4(self, result: ValidationResult) -> bool:
        """PARTIAL_PASS → skip agent4, đi thẳng agent5 (code OK, logic sai)."""
        return result.status == ValidationStatus.PARTIAL_PASS

    def can_retry(self, result: ValidationResult) -> bool:
        """Trả về True nếu còn có thể retry, False nếu nên dừng."""
        if result.status == ValidationStatus.PASS:
            return False
        if result.status == ValidationStatus.CODE_ERROR:
            # Adaptive escalation check
            if self.should_escalate(result):
                return True
            if self.counts["agent4"] < self.max_retries["agent4"]:
                return True
            return False
        if result.status in (ValidationStatus.WRONG_RESULT, ValidationStatus.PARTIAL_PASS):
            return self.counts["agent5"] < self.max_retries["agent5"]
        return False  # FAILED_* hoặc SCHEMA_ERROR → dừng

    def get_trace(self) -> list[dict]:
        return list(self._trace)
