"""
Routing logic: Dựa vào ValidationResult, quyết định chuyển cho Agent nào và truyền context gì.
Kèm retry_counts và error_history để agent biết đang ở lần retry nào và đã thử gì.

Adaptive routing: dùng error classification để chọn agent phù hợp, escalate sớm khi cần.
"""

from schemas.validation_schemas import ValidationResult, ValidationStatus
from schemas.block_schemas import BlockMappingData
from schemas.diff_schemas import ConfigDiscovery
from pipeline.retry import classify_error, RetryManager


def route_validation(
    result: ValidationResult,
    block_data: BlockMappingData,
    retry_counts: dict[str, int] | None = None,
    max_retries: dict[str, int] | None = None,
    error_history: list[str] | None = None,
    retry_manager: RetryManager | None = None,
    config_discovery: ConfigDiscovery | None = None,
) -> tuple[str, str]:
    """Quyết định agent tiếp theo.

    Args:
        result: Kết quả validation từ Agent 3.
        block_data: Thông tin block từ Agent 1.
        retry_counts: Số lần retry đã thực hiện cho mỗi agent.
        max_retries: Giới hạn retry cho mỗi agent (dùng cho escalation logic).
        error_history: Danh sách lỗi từ các lần retry trước.
        retry_manager: RetryManager instance (cho adaptive escalation).
        config_discovery: Ground truth từ Agent 1.5 (nếu có).

    Returns:
        (next_agent, context_message)
        next_agent: "agent4" | "agent5" | "done" | "failed"
    """
    counts = retry_counts or {}

    if result.status == ValidationStatus.PASS:
        return ("done", "")

    if result.status == ValidationStatus.CODE_ERROR:
        agent4_count = counts.get("agent4", 0)
        agent4_max = max_retries.get("agent4", 3) if max_retries else 3
        error_cat = classify_error(result)

        # Adaptive escalation: dùng RetryManager nếu có, fallback sang count check
        should_escalate = (
            retry_manager.should_escalate(result) if retry_manager
            else agent4_count >= agent4_max
        )

        if should_escalate:
            context = (
                f"⚠ ESCALATION: Agent 4 đã fix {agent4_count} lần nhưng code vẫn lỗi.\n"
                f"Loại lỗi: {error_cat} — Có thể XPath/logic SAI GỐC — cần điều tra lại model XML.\n\n"
                f"File code: {result.code_file_path}\n"
                f"Test case fail: {result.failed_test_case or 'N/A'}\n"
                f"Stderr lần cuối:\n{result.stderr}\n"
                f"Block config analysis: {block_data.config_map_analysis}\n"
                f"Đây là lần điều tra thứ {counts.get('agent5', 0) + 1}\n\n"
                f"💡 Dùng read_raw_block_config(block_sid) nếu cần xem TOÀN BỘ raw config."
            )
            if error_history:
                context += (
                    f"\n\n⚠ Toàn bộ lịch sử lỗi (Agent 4 đã thất bại — cần approach MỚI HOÀN TOÀN):\n"
                )
                for i, err in enumerate(error_history, 1):
                    context += f"  {i}. {err}\n"
            return ("agent5", _append_discovery_context(context, config_discovery))

        attempt = agent4_count + 1
        context = (
            f"File bị lỗi: {result.code_file_path}\n"
            f"Test case fail: {result.failed_test_case or 'N/A'}\n"
            f"Stderr:\n{result.stderr}\n"
            f"Đây là lần fix thứ {attempt}"
        )
        if error_history:
            context += (
                f"\n\n⚠ Lịch sử lỗi TRƯỚC ĐÓ (KHÔNG lặp lại cách fix đã thất bại):\n"
            )
            for i, err in enumerate(error_history, 1):
                context += f"  {i}. {err}\n"
        return ("agent4", context)

    if result.status in (ValidationStatus.WRONG_RESULT, ValidationStatus.PARTIAL_PASS):
        attempt = counts.get("agent5", 0) + 1
        agent5_max = max_retries.get("agent5", 3) if max_retries else 3
        is_last_retry = attempt >= agent5_max

        partial_note = ""
        if result.status == ValidationStatus.PARTIAL_PASS:
            partial_note = (
                f"\n⚠ PARTIAL PASS: {result.test_cases_passed}/{result.test_cases_total} "
                f"test cases passed — code chạy được nhưng logic KHÔNG đúng cho mọi model.\n"
            )

        context = (
            f"File code: {result.code_file_path}\n"
            f"Test case fail: {result.failed_test_case or 'N/A'}\n"
            f"{partial_note}"
            f"Actual result: {result.actual_result}\n"
            f"Expected result: {result.expected_result}\n"
            f"Block config analysis: {block_data.config_map_analysis}\n"
            f"Đây là lần điều tra thứ {attempt}"
        )
        if is_last_retry:
            context += (
                f"\n\n🔴 ĐÂY LÀ LẦN RETRY CUỐI — dùng read_raw_block_config() để đọc "
                f"TOÀN BỘ raw config của block gây lỗi. Không bỏ sót gì."
            )
        if error_history:
            context += (
                f"\n\n⚠ Lịch sử điều tra TRƯỚC ĐÓ (KHÔNG lặp lại approach đã thất bại):\n"
            )
            for i, err in enumerate(error_history, 1):
                context += f"  {i}. {err}\n"
        return ("agent5", _append_discovery_context(context, config_discovery))

    return ("failed", f"Trạng thái không xử lý được: {result.status}")


def _append_discovery_context(context: str, config_discovery: ConfigDiscovery | None) -> str:
    """Append ConfigDiscovery ground truth vào context cho Agent 5."""
    if not config_discovery:
        return context
    return context + (
        f"\n\nCONFIG DISCOVERY (ground truth from model diff — Agent 1.5):\n"
        f"  location_type: {config_discovery.location_type}\n"
        f"  xpath_pattern: {config_discovery.xpath_pattern}\n"
        f"  default_value: {config_discovery.default_value}\n"
        f"  notes: {config_discovery.notes}"
    )
