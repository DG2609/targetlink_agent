"""
State machine cho retry loop sau Agent 3 (Validator).

Tập trung TOÀN BỘ logic routing và escalation vào 1 chỗ duy nhất:
  - Khi nào chuyển Agent 4 (Bug Fixer)?
  - Khi nào escalate sang Agent 5 (Inspector)?
  - Khi nào dừng (DONE / FAILED)?
  - Context message cho mỗi agent?

Trước đây logic nằm rải rác ở router.py + retry.py + runner.py.
Giờ developer chỉ cần đọc file này để hiểu toàn bộ retry flow.
"""

import json
import logging
from enum import Enum

from schemas.validation_schemas import ValidationResult, ValidationStatus
from schemas.block_schemas import BlockMappingData
from schemas.diff_schemas import ConfigDiscovery
from schemas.report_schemas import TraceEntry
from schemas.agent_inputs import Agent4Input, Agent5Input
from pipeline.retry import classify_error, ErrorCategory, EARLY_ESCALATE_AFTER

logger = logging.getLogger(__name__)


class RetryState(str, Enum):
    """Trạng thái trong retry loop."""
    VALIDATE = "validate"     # Chạy Agent 3
    BUG_FIX = "bug_fix"      # Chạy Agent 4
    INSPECT = "inspect"       # Chạy Agent 5
    DONE = "done"             # PASS — dừng
    FAILED = "failed"         # Hết budget — dừng


class RetryStateMachine:
    """Điều phối retry loop với state transitions rõ ràng.

    Quy tắc chuyển trạng thái (từ kết quả VALIDATE):

    ┌──────────────────┬───────────────────────────────────────────┐
    │ ValidationStatus │ Next State                                │
    ├──────────────────┼───────────────────────────────────────────┤
    │ PASS             │ DONE                                      │
    │ CODE_ERROR       │ BUG_FIX (nếu agent4 còn budget)          │
    │                  │ INSPECT (nếu cần escalate hoặc hết a4)   │
    │                  │ FAILED  (nếu hết cả a4 + a5)             │
    │ WRONG_RESULT     │ INSPECT (nếu agent5 còn budget)          │
    │ PARTIAL_PASS     │ INSPECT (luôn skip Agent 4)              │
    │                  │ FAILED  (nếu hết a5)                     │
    │ Khác             │ FAILED                                    │
    └──────────────────┴───────────────────────────────────────────┘

    BUG_FIX → VALIDATE (luôn re-validate sau fix)
    INSPECT → VALIDATE (luôn re-validate sau inspect)
    """

    def __init__(self, max_agent4: int = 3, max_agent5: int = 3):
        self.max_agent4 = max_agent4
        self.max_agent5 = max_agent5
        self.agent4_count = 0
        self.agent5_count = 0
        self.state = RetryState.VALIDATE
        self._error_history: list[str] = []
        self._trace: list[TraceEntry] = []
        self._last_dedup_attempts: int = -1

    @property
    def error_history(self) -> list[str]:
        """Public accessor for error history (used by Agent5Input)."""
        return list(self._error_history)

    # ── State transitions ────────────────────────────

    def next_state(self, validation: ValidationResult) -> RetryState:
        """Quyết định trạng thái tiếp theo dựa vào kết quả validation.

        Đây là HÀM DUY NHẤT quyết định routing — không có logic routing ở đâu khác.
        """
        prev_state = self.state

        if validation.status == ValidationStatus.PASS:
            self.state = RetryState.DONE
            logger.debug(
                "State transition: %s → %s (reason: validation PASS)",
                prev_state, self.state,
            )
            return self.state

        if validation.status == ValidationStatus.CODE_ERROR:
            self.state = self._route_code_error(validation)
            logger.debug(
                "State transition: %s → %s (reason: CODE_ERROR, agent4=%d, agent5=%d)",
                prev_state, self.state, self.agent4_count, self.agent5_count,
            )
            if self.state == RetryState.FAILED:
                logger.error(
                    "State reached FAILED: budget exhausted after CODE_ERROR "
                    "(agent4=%d/%d, agent5=%d/%d)",
                    self.agent4_count, self.max_agent4,
                    self.agent5_count, self.max_agent5,
                )
            return self.state

        if validation.status in (ValidationStatus.WRONG_RESULT, ValidationStatus.PARTIAL_PASS):
            # Logic error / partial → luôn Agent 5 (Agent 4 chỉ fix crash, không fix logic)
            if self.agent5_count < self.max_agent5:
                self.state = RetryState.INSPECT
            else:
                self.state = RetryState.FAILED
            logger.debug(
                "State transition: %s → %s (reason: %s, agent5=%d)",
                prev_state, self.state, validation.status.value, self.agent5_count,
            )
            if self.state == RetryState.FAILED:
                logger.error(
                    "State reached FAILED: budget exhausted after %s "
                    "(agent4=%d/%d, agent5=%d/%d)",
                    validation.status.value,
                    self.agent4_count, self.max_agent4,
                    self.agent5_count, self.max_agent5,
                )
            return self.state

        # SCHEMA_ERROR, FAILED_* → dừng
        self.state = RetryState.FAILED
        logger.debug(
            "State transition: %s → %s (reason: terminal status %s)",
            prev_state, self.state, validation.status.value,
        )
        logger.error(
            "State reached FAILED: terminal validation status %s "
            "(agent4=%d/%d, agent5=%d/%d)",
            validation.status.value,
            self.agent4_count, self.max_agent4,
            self.agent5_count, self.max_agent5,
        )
        return self.state

    def _route_code_error(self, validation: ValidationResult) -> RetryState:
        """CODE_ERROR routing: Agent 4 hay escalate Agent 5?

        Adaptive escalation: loại lỗi quyết định escalate sớm hay muộn.
        VD: SyntaxError → escalate sau 1 lần. XPathError → sau 2 lần.
        """
        error_cat = classify_error(validation)
        escalate_after = EARLY_ESCALATE_AFTER.get(error_cat, self.max_agent4)
        should_escalate = self.agent4_count >= min(escalate_after, self.max_agent4)

        if not should_escalate and self.agent4_count < self.max_agent4:
            return RetryState.BUG_FIX

        # Escalate sang Agent 5
        if self.agent5_count < self.max_agent5:
            return RetryState.INSPECT

        return RetryState.FAILED

    # ── Counter & tracking ───────────────────────────

    def increment(self, agent_name: str) -> None:
        """Tăng counter (gọi TRƯỚC khi run agent)."""
        if agent_name == "agent4":
            self.agent4_count += 1
        elif agent_name == "agent5":
            self.agent5_count += 1
        self._trace.append(TraceEntry(
            agent=agent_name,
            attempt=self.agent4_count if agent_name == "agent4" else self.agent5_count,
        ))

    def get_trace(self) -> list[TraceEntry]:
        return list(self._trace)

    # ── Error tracking ───────────────────────────────

    def record_error(self, validation: ValidationResult) -> None:
        """Ghi nhận lỗi trước khi retry — agent sau sẽ biết đã thử gì.

        Tự dedup: không ghi lỗi giống hệt lần trước
        (xảy ra khi LLM call fail → same validation lặp lại).
        """
        tc_info = f" [test_case={validation.failed_test_case}]" if validation.failed_test_case else ""
        error_cat = classify_error(validation)

        if validation.status == ValidationStatus.CODE_ERROR:
            stderr_short = (validation.stderr or "")[:300]
            entry = f"CODE_ERROR({error_cat}){tc_info}: {stderr_short}"
        elif validation.status in (ValidationStatus.WRONG_RESULT, ValidationStatus.PARTIAL_PASS):
            actual_short = json.dumps(validation.actual_result)[:200] if validation.actual_result else "None"
            expected_short = json.dumps(validation.expected_result)[:200] if validation.expected_result else "None"
            pass_info = f" [{validation.test_cases_passed}/{validation.test_cases_total} passed]"
            entry = (
                f"{validation.status.value}({error_cat}){tc_info}{pass_info}: "
                f"actual={actual_short}, expected={expected_short}"
            )
        else:
            entry = f"{validation.status.value}({error_cat}){tc_info}"

        # Dedup: skip chỉ khi HOÀN TOÀN giống entry cuối VÀ cùng retry iteration
        # (cùng error + cùng test case + chưa có retry nào chạy giữa = LLM fail lặp lại)
        total_attempts = self.agent4_count + self.agent5_count
        if (
            self._error_history
            and self._error_history[-1] == entry
            and getattr(self, "_last_dedup_attempts", -1) == total_attempts
        ):
            logger.debug(
                "Duplicate error skipped (no new retry since last record): category=%s, agent4=%d, agent5=%d",
                error_cat, self.agent4_count, self.agent5_count,
            )
            return
        self._last_dedup_attempts = total_attempts
        self._error_history.append(entry)
        logger.warning(
            "Error recorded: category=%s, agent4=%d, agent5=%d",
            error_cat, self.agent4_count, self.agent5_count,
        )

    # ── Context builders ─────────────────────────────

    def build_agent4_context(self, validation: ValidationResult) -> str:
        """Build context message cho Agent 4 (Bug Fixer).

        Dùng Agent4Input schema → to_prompt() để format nhất quán.
        """
        inp = Agent4Input(
            rule_id=validation.rule_id,
            code_file_path=validation.code_file_path,
            failed_test_case=validation.failed_test_case or "N/A",
            stderr=validation.stderr or "",
            attempt=self.agent4_count,
            error_history=self.error_history,
        )
        return inp.to_prompt()

    def build_agent5_context(
        self,
        validation: ValidationResult,
        block_data: BlockMappingData,
        config_discovery: ConfigDiscovery | None = None,
        exploration_summary: str = "",
        previous_findings: list[str] | None = None,
        parsed_rule=None,
    ) -> str:
        """Build context message cho Agent 5 (Inspector).

        Dùng Agent5Input schema → to_prompt() để format nhất quán.

        Args:
            exploration_summary: Knowledge handoff từ Agent 2 (Fix A).
            previous_findings: Investigation notes từ Agent 5 retries trước (Fix B).
            parsed_rule: ParsedRule object — condition/expected_value cho Agent 5.
        """
        inp = Agent5Input.from_state_machine(
            validation=validation,
            block_data=block_data,
            sm=self,
            config_discovery=config_discovery,
            exploration_summary=exploration_summary,
            previous_findings=previous_findings,
            parsed_rule=parsed_rule,
        )
        return inp.to_prompt()

    # ── Finalization ─────────────────────────────────

    def mark_final_status(self, validation: ValidationResult) -> ValidationResult:
        """Đánh dấu FAILED_* status khi hết retry. Trả về ValidationResult mới (không mutate)."""
        status_map = {
            ValidationStatus.CODE_ERROR: ValidationStatus.FAILED_CODE_ERROR,
            ValidationStatus.WRONG_RESULT: ValidationStatus.FAILED_WRONG_RESULT,
            ValidationStatus.PARTIAL_PASS: ValidationStatus.FAILED_PARTIAL_PASS,
        }
        new_status = status_map.get(validation.status, validation.status)
        return validation.model_copy(update={"status": new_status})
