"""
Truncation layer cho tool output — bảo vệ context window của LLM.

Pattern từ reference codebase (agentic/agent/tools/truncation.py):
  Mọi tool output qua truncate_output() trước khi trả về agent.
  MAX 30KB / 500 dòng. Kèm hint để agent biết cách xem thêm.
"""


def truncate_output(
    output: str,
    max_chars: int = 30_000,
    max_lines: int = 500,
) -> str:
    """Cắt tool output nếu quá lớn để bảo vệ context window.

    Args:
        output: Raw tool output string.
        max_chars: Giới hạn ký tự tối đa (default 30KB).
        max_lines: Giới hạn số dòng tối đa (default 500).

    Returns:
        Output đã truncate (nếu cần), kèm warning cho agent.
    """
    if not output:
        return output

    lines = output.splitlines()
    truncated = False

    # Bước 1: Cắt theo số dòng
    if len(lines) > max_lines:
        original_count = len(lines)
        lines = lines[:max_lines]
        lines.append(
            f"\n... [{original_count - max_lines} dòng bị cắt — "
            f"dùng XPath/regex cụ thể hơn để thu hẹp kết quả]"
        )
        truncated = True
        output = "\n".join(lines)

    # Bước 2: Cắt theo ký tự (sau khi đã cắt dòng)
    if len(output) > max_chars:
        output = output[:max_chars] + (
            f"\n... [output bị cắt tại {max_chars} ký tự — "
            f"thu hẹp query hoặc chỉ định file XML cụ thể hơn]"
        )

    return output
