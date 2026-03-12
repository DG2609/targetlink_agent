"""
Tools cho việc thực thi code trong sandbox và so sánh kết quả.

Agent 3 (Validator) sử dụng toolkit này.

Code được chạy trong subprocess cách ly — nếu code crash, main process không bị ảnh hưởng.
Generated code nhận model_dir (thư mục XML tree) qua sys.argv[1].
"""

import json
import subprocess
import sys
from pathlib import Path
from agno.tools import Toolkit


class SandboxToolkit(Toolkit):
    """Cung cấp khả năng chạy code sandbox và đánh giá kết quả cho Agent.

    Sandbox = subprocess isolation. Code do LLM sinh ra được chạy trong process riêng
    với timeout, không ảnh hưởng main pipeline.
    """

    def __init__(self, model_dir: str, timeout: int = 30):
        super().__init__(name="sandbox_tools")
        self.model_dir = model_dir
        self.timeout = timeout

        self.register(self.sandbox_execute_python)
        self.register(self.compare_json_result)

    # ──────────────────────────────────────────────
    # Tool 1: sandbox_execute_python
    # ──────────────────────────────────────────────

    def sandbox_execute_python(self, file_path: str) -> str:
        """Chạy file Python trong subprocess cách ly (sandbox).
        Tự động truyền đường dẫn thư mục model (XML tree) làm argument đầu tiên.

        Timeout mặc định 30 giây. Nếu code chạy quá lâu → bị kill.
        Trả về cả stdout (kết quả) và stderr (lỗi nếu có).

        Args:
            file_path: Đường dẫn tới file Python cần chạy (VD: "generated_checks/check_rule_R001.py").

        Returns:
            JSON gồm: exit_code, stdout, stderr, timed_out.
            exit_code=0 nghĩa là code chạy OK, khác 0 là có lỗi.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return json.dumps({
                "exit_code": -1,
                "stdout": "",
                "stderr": f"File không tồn tại: {file_path}",
                "timed_out": False,
            })

        try:
            result = subprocess.run(
                [sys.executable, str(file_path.resolve()), self.model_dir],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(file_path.parent),
            )

            output = {
                "exit_code": result.returncode,
                "stdout": result.stdout[-5000:] if len(result.stdout) > 5000 else result.stdout,
                "stderr": result.stderr[-3000:] if len(result.stderr) > 3000 else result.stderr,
                "timed_out": False,
            }

        except subprocess.TimeoutExpired:
            output = {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"TIMEOUT: Code chạy quá {self.timeout} giây, đã bị kill.",
                "timed_out": True,
            }

        except OSError as e:
            output = {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"OS Error khi chạy subprocess: {e}",
                "timed_out": False,
            }

        return json.dumps(output, indent=2, ensure_ascii=False)

    # ──────────────────────────────────────────────
    # Tool 2: compare_json_result
    # ──────────────────────────────────────────────

    def compare_json_result(self, actual_json: str, expected_json: str) -> str:
        """So sánh kết quả thực tế (từ stdout của code) với kết quả mong đợi (từ test case).
        Kiểm tra các trường chính: total_blocks, pass_count, fail_count.

        Dùng SAU KHI sandbox_execute_python chạy OK (exit_code=0) để đánh giá code đúng/sai.

        Args:
            actual_json: JSON string từ stdout của code vừa chạy.
            expected_json: JSON string từ expected_results.json cho rule này.

        Returns:
            JSON gồm: match (bool), differences (list mô tả chênh lệch), summary.
        """
        # Parse actual
        try:
            actual = json.loads(actual_json)
        except (json.JSONDecodeError, TypeError) as e:
            return json.dumps({
                "match": False,
                "error": f"Không parse được actual JSON: {e}",
                "actual_raw": str(actual_json)[:500],
            }, ensure_ascii=False)

        # Parse expected
        try:
            expected = json.loads(expected_json) if isinstance(expected_json, str) else expected_json
        except (json.JSONDecodeError, TypeError) as e:
            return json.dumps({
                "match": False,
                "error": f"Không parse được expected JSON: {e}",
                "expected_raw": str(expected_json)[:500],
            }, ensure_ascii=False)

        # So sánh các trường chính
        differences = []
        fields_to_check = [
            ("total_blocks", "expected_total_blocks"),
            ("pass_count", "expected_pass"),
            ("fail_count", "expected_fail"),
        ]

        for actual_key, expected_key in fields_to_check:
            actual_val = actual.get(actual_key)
            expected_val = expected.get(expected_key)

            if expected_val is not None and actual_val != expected_val:
                differences.append({
                    "field": actual_key,
                    "actual": actual_val,
                    "expected": expected_val,
                    "diff": (actual_val or 0) - (expected_val or 0),
                })

        is_match = len(differences) == 0

        result = {
            "match": is_match,
            "differences": differences,
            "summary": "PASS — Kết quả khớp expected." if is_match
                       else f"MISMATCH — {len(differences)} trường khác biệt.",
            "actual_summary": {
                "total_blocks": actual.get("total_blocks"),
                "pass_count": actual.get("pass_count"),
                "fail_count": actual.get("fail_count"),
            },
            "expected_summary": {
                "total_blocks": expected.get("expected_total_blocks"),
                "pass": expected.get("expected_pass"),
                "fail": expected.get("expected_fail"),
            },
        }

        return json.dumps(result, indent=2, ensure_ascii=False)
