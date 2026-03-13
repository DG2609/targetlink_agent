"""
Phát hiện agent gọi tool lặp lại liên tiếp với cùng arguments.
Khi phát hiện loop (mặc định 3 lần), trả về recovery hint thay vì chạy tool.

Pattern từ reference codebase (agentic/agent/nodes.py):
  3 identical consecutive tool calls → recovery hint injected.
"""

import hashlib
import json


class LoopDetector:
    """Track tool calls và phát hiện repeated calls liên tiếp."""

    def __init__(self, max_repeats: int = 3):
        self.max_repeats = max_repeats
        self._history: list[tuple[str, str]] = []

    def check(self, tool_name: str, **kwargs) -> str | None:
        """Kiểm tra xem tool call có bị lặp liên tiếp không.

        Args:
            tool_name: Tên tool đang được gọi.
            **kwargs: Arguments của tool call.

        Returns:
            Recovery hint string nếu loop detected, None nếu OK tiếp tục.
        """
        args_str = json.dumps(kwargs, sort_keys=True, default=str)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()[:12]
        sig = (tool_name, args_hash)

        self._history.append(sig)

        # Đếm lần gọi liên tiếp cùng signature
        consecutive = 0
        for prev in reversed(self._history):
            if prev == sig:
                consecutive += 1
            else:
                break

        if consecutive >= self.max_repeats:
            return (
                f"⚠ LOOP DETECTED: Bạn đã gọi {tool_name}() với CÙNG arguments "
                f"{consecutive} lần liên tiếp — kết quả sẽ KHÔNG thay đổi.\n"
                f"Hãy thử 1 trong các cách sau:\n"
                f"  1. Thay đổi arguments (dùng regex/xpath KHÁC)\n"
                f"  2. Tìm kiếm trong FILE XML KHÁC\n"
                f"  3. Nếu thông tin đã đủ, hãy viết code dựa trên những gì đã biết\n"
                f"  4. Nếu block/config không tồn tại trong model, ghi nhận và tiếp tục"
            )
        return None

    def reset(self) -> None:
        """Reset history — gọi khi bắt đầu task mới hoặc agent mới."""
        self._history.clear()
