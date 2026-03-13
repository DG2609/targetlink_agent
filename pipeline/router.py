"""
Routing logic: Dựa vào ValidationResult, quyết định chuyển cho Agent nào và truyền context gì.
Kèm retry_counts và error_history để agent biết đang ở lần retry nào và đã thử gì.
"""

from schemas.validation_schemas import ValidationResult, ValidationStatus
from schemas.block_schemas import BlockMappingData


def route_validation(
    result: ValidationResult,
    block_data: BlockMappingData,
    retry_counts: dict[str, int] | None = None,
    max_retries: dict[str, int] | None = None,
    error_history: list[str] | None = None,
) -> tuple[str, str]:
    """Quyết định agent tiếp theo.

    Args:
        result: Kết quả validation từ Agent 3.
        block_data: Thông tin block từ Agent 1.
        retry_counts: Số lần retry đã thực hiện cho mỗi agent.
        max_retries: Giới hạn retry cho mỗi agent (dùng cho escalation logic).
        error_history: Danh sách lỗi từ các lần retry trước.

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

        # Escalation: Agent 4 hết retry → chuyển sang Agent 5 điều tra gốc rễ
        if agent4_count >= agent4_max:
            context = (
                f"⚠ ESCALATION: Agent 4 đã fix {agent4_count} lần nhưng code vẫn lỗi.\n"
                f"Có thể XPath/logic SAI GỐC — cần điều tra lại model XML.\n\n"
                f"File code: {result.code_file_path}\n"
                f"Stderr lần cuối:\n{result.stderr}\n"
                f"Block config analysis: {block_data.config_map_analysis}\n"
                f"Đây là lần điều tra thứ {counts.get('agent5', 0) + 1}"
            )
            if error_history:
                context += (
                    f"\n\n⚠ Toàn bộ lịch sử lỗi (Agent 4 đã thất bại — cần approach MỚI HOÀN TOÀN):\n"
                )
                for i, err in enumerate(error_history, 1):
                    context += f"  {i}. {err}\n"
            return ("agent5", context)

        attempt = agent4_count + 1
        context = (
            f"File bị lỗi: {result.code_file_path}\n"
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

    if result.status == ValidationStatus.WRONG_RESULT:
        attempt = counts.get("agent5", 0) + 1
        context = (
            f"File code: {result.code_file_path}\n"
            f"Actual result: {result.actual_result}\n"
            f"Expected result: {result.expected_result}\n"
            f"Block config analysis: {block_data.config_map_analysis}\n"
            f"Đây là lần điều tra thứ {attempt}"
        )
        if error_history:
            context += (
                f"\n\n⚠ Lịch sử điều tra TRƯỚC ĐÓ (KHÔNG lặp lại approach đã thất bại):\n"
            )
            for i, err in enumerate(error_history, 1):
                context += f"  {i}. {err}\n"
        return ("agent5", context)

    return ("failed", f"Trạng thái không xử lý được: {result.status}")
