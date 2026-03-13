"""
Quản lý retry và escalation policy.
Agent 4 xử lý CODE_ERROR, Agent 5 xử lý WRONG_RESULT — mỗi cái có max_retries RIÊNG.
Theo dõi error history để agent biết những gì đã thử, tránh lặp lại approach cũ.
"""

from schemas.validation_schemas import ValidationResult, ValidationStatus


class RetryManager:
    """Theo dõi số lần retry, error history, và quyết định có nên tiếp tục không."""

    def __init__(self, max_retries_agent4: int = 3, max_retries_agent5: int = 3):
        self.max_retries = {
            "agent4": max_retries_agent4,
            "agent5": max_retries_agent5,
        }
        self.counts: dict[str, int] = {"agent4": 0, "agent5": 0}
        self._trace: list[dict] = []
        self._error_history: list[str] = []

    def increment(self, agent_name: str) -> None:
        self.counts[agent_name] = self.counts.get(agent_name, 0) + 1
        self._trace.append({
            "agent": agent_name,
            "attempt": self.counts[agent_name],
        })

    def add_error(self, error_summary: str) -> None:
        """Ghi nhận lỗi để truyền cho agent ở lần retry sau."""
        self._error_history.append(error_summary)

    def get_error_history(self) -> list[str]:
        return list(self._error_history)

    def should_escalate(self, result: ValidationResult) -> bool:
        """CODE_ERROR hết retry Agent 4 → escalate sang Agent 5.

        Khi Agent 4 fix lòng vòng cùng bug 3 lần, có thể XPath sai gốc.
        Chuyển sang Agent 5 điều tra model thay vì tiếp tục patch code.
        """
        return (
            result.status == ValidationStatus.CODE_ERROR
            and self.counts["agent4"] >= self.max_retries["agent4"]
            and self.counts["agent5"] < self.max_retries["agent5"]
        )

    def can_retry(self, result: ValidationResult) -> bool:
        """Trả về True nếu còn có thể retry, False nếu nên dừng."""
        if result.status == ValidationStatus.PASS:
            return False
        if result.status == ValidationStatus.CODE_ERROR:
            if self.counts["agent4"] < self.max_retries["agent4"]:
                return True
            # Escalation: Agent 4 hết retry → chuyển sang Agent 5
            return self.should_escalate(result)
        if result.status == ValidationStatus.WRONG_RESULT:
            return self.counts["agent5"] < self.max_retries["agent5"]
        return False  # FAILED_* hoặc SCHEMA_ERROR → dừng

    def get_trace(self) -> list[dict]:
        return list(self._trace)
