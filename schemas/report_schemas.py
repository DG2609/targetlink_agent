"""
Schemas cho kết quả cuối cùng.
  - PipelineStep: 1 bước trong pipeline (agent call + timing)
  - RuleReport: kết quả 1 rule
  - FinalReport: báo cáo tổng hợp
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

from schemas.validation_schemas import ValidationStatus, ValidationResult


class PipelineStep(BaseModel):
    """1 bước trong pipeline — tracking agent call + timing."""
    agent_name: str = Field(description="Tên agent, VD: 'Agent 0 (Rule Analyzer)'")
    started_at: str = Field(default="", description="ISO timestamp bắt đầu")
    finished_at: str = Field(default="", description="ISO timestamp kết thúc")
    duration_seconds: float = Field(default=0.0, description="Thời gian chạy (seconds)")
    status: str = Field(default="success", description="Trạng thái: 'success', 'error', 'skipped'")
    input_summary: str = Field(default="", description="Tóm tắt input cho step")
    output_summary: str = Field(default="", description="Tóm tắt output từ step")


class TraceEntry(BaseModel):
    """1 entry trong retry trace — agent nào chạy lần thứ mấy."""
    agent: str = Field(description="Agent name: 'agent4' hoặc 'agent5'")
    attempt: int = Field(description="Lần thứ mấy (1-based)")


class RuleReport(BaseModel):
    """Kết quả xử lý 1 rule qua toàn bộ pipeline."""
    rule_id: str
    status: ValidationStatus
    match_expected: bool = False
    actual: Optional[dict] = None
    expected: Optional[dict] = None
    generated_script: str = ""
    needs_human_review: bool = False
    pipeline_trace: list[TraceEntry] = Field(default_factory=list)
    pipeline_steps: list[PipelineStep] = Field(default_factory=list)
    rule_duration_seconds: float = 0.0
    error_detail: Optional[str] = None

    @classmethod
    def from_validation(
        cls,
        rule_id: str,
        result: "ValidationResult",
        trace: list[TraceEntry],
    ) -> "RuleReport":
        is_pass = result.status == ValidationStatus.PASS
        is_failed = result.status in (
            ValidationStatus.FAILED_CODE_ERROR,
            ValidationStatus.FAILED_WRONG_RESULT,
            ValidationStatus.FAILED_PARTIAL_PASS,
        )
        return cls(
            rule_id=rule_id,
            status=result.status,
            match_expected=is_pass,
            actual=result.actual_result,
            expected=result.expected_result,
            generated_script=result.code_file_path,
            needs_human_review=is_failed,
            pipeline_trace=trace,
            error_detail=result.stderr if is_failed else None,
        )


class FinalReport(BaseModel):
    """Báo cáo tổng hợp toàn bộ pipeline."""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_file: str
    total_rules: int
    results: list[RuleReport]
    total_duration_seconds: float = 0.0

    @property
    def summary(self) -> dict:
        partial = sum(
            1 for r in self.results
            if r.status == ValidationStatus.FAILED_PARTIAL_PASS
        )
        return {
            "pass": sum(1 for r in self.results if r.status == ValidationStatus.PASS),
            "partial_pass": partial,
            "failed": sum(1 for r in self.results if r.needs_human_review),
            "total": self.total_rules,
        }
