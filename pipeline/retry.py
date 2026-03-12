"""
Quản lý retry và escalation policy.
Agent 4 xử lý CODE_ERROR, Agent 5 xử lý WRONG_RESULT — mỗi cái tối đa MAX_RETRIES lần.
"""

from schemas.validation_schemas import ValidationResult, ValidationStatus


class RetryManager:
    """Theo dõi số lần retry và quyết định có nên tiếp tục không."""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.counts: dict[str, int] = {"agent4": 0, "agent5": 0}
        self._trace: list[dict] = []

    def increment(self, agent_name: str) -> None:
        self.counts[agent_name] = self.counts.get(agent_name, 0) + 1
        self._trace.append({
            "agent": agent_name,
            "attempt": self.counts[agent_name],
        })

    def can_retry(self, result: ValidationResult) -> bool:
        """Trả về True nếu còn có thể retry, False nếu nên dừng."""
        if result.status == ValidationStatus.PASS:
            return False
        if result.status == ValidationStatus.CODE_ERROR:
            return self.counts["agent4"] < self.max_retries
        if result.status == ValidationStatus.WRONG_RESULT:
            return self.counts["agent5"] < self.max_retries
        return False  # FAILED_* hoặc SCHEMA_ERROR → dừng

    def get_trace(self) -> list[dict]:
        return list(self._trace)
