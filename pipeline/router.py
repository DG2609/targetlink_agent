"""
Routing logic: Dựa vào ValidationResult, quyết định chuyển cho Agent nào và truyền context gì.
"""

from schemas.validation_schemas import ValidationResult, ValidationStatus
from schemas.block_schemas import BlockMappingData


def route_validation(
    result: ValidationResult,
    block_data: BlockMappingData,
) -> tuple[str, str]:
    """Quyết định agent tiếp theo.

    Returns:
        (next_agent, context_message)
        next_agent: "agent4" | "agent5" | "done" | "failed"
    """
    if result.status == ValidationStatus.PASS:
        return ("done", "")

    if result.status == ValidationStatus.CODE_ERROR:
        context = (
            f"File bị lỗi: {result.code_file_path}\n"
            f"Stderr:\n{result.stderr}\n"
            f"Lần retry: {result.retry_count}"
        )
        return ("agent4", context)

    if result.status == ValidationStatus.WRONG_RESULT:
        context = (
            f"File code: {result.code_file_path}\n"
            f"Actual result: {result.actual_result}\n"
            f"Expected result: {result.expected_result}\n"
            f"Block config analysis: {block_data.config_map_analysis}\n"
            f"Lần retry: {result.retry_count}"
        )
        return ("agent5", context)

    return ("failed", f"Trạng thái không xử lý được: {result.status}")
