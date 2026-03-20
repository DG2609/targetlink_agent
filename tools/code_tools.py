"""
Tools cho việc sinh, đọc, và sửa file Python code.

Agents sử dụng:
  - Agent 2 (Code Generator): write_python_file
  - Agent 4 (Bug Fixer): read_python_file, read_error_traceback, patch_python_file
  - Agent 5 (Inspector): rewrite_advanced_code
"""

import ast
import json
import re
from pathlib import Path
from agno.tools import Toolkit


class CodeToolkit(Toolkit):
    """Cung cấp khả năng sinh và sửa code Python cho Agent.

    Tất cả file write CHỈ được phép ghi vào thư mục output_dir (generated_checks/).
    Không bao giờ ghi ra ngoài thư mục này.
    """

    def __init__(self, output_dir: str = "generated_checks"):
        super().__init__(name="code_tools")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.register(self.write_python_file)
        self.register(self.read_python_file)
        self.register(self.read_error_traceback)
        self.register(self.patch_python_file)
        self.register(self.rewrite_advanced_code)

    def _safe_path(self, filename: str) -> Path:
        """Đảm bảo file path nằm trong output_dir. Chặn path traversal."""
        # Chỉ lấy tên file, bỏ hết path components
        safe_name = Path(filename).name
        if not safe_name.endswith(".py"):
            safe_name += ".py"
        return self.output_dir / safe_name

    # ──────────────────────────────────────────────
    # Tool 1: write_python_file
    # ──────────────────────────────────────────────

    def write_python_file(self, filename: str, code_content: str) -> str:
        """Tạo file Python mới trong thư mục generated_checks/.
        GHI ĐÈ nếu file đã tồn tại.

        Dùng khi Agent 2 sinh code check rule mới.

        Args:
            filename: Tên file (VD: "check_rule_R001.py"). Tự động thêm .py nếu thiếu.
            code_content: Nội dung code Python hoàn chỉnh.

        Returns:
            Đường dẫn tuyệt đối tới file đã tạo, hoặc thông báo lỗi.
        """
        file_path = self._safe_path(filename)

        # Syntax check trước khi ghi — bắt lỗi sớm, không chờ Agent 3
        try:
            ast.parse(code_content)
        except SyntaxError as e:
            return (
                f"SYNTAX ERROR — code không hợp lệ, KHÔNG ghi file.\n"
                f"  Line {e.lineno}: {e.msg}\n"
                f"  {e.text.strip() if e.text else ''}\n"
                f"Sửa lỗi syntax rồi gọi lại write_python_file()."
            )

        try:
            file_path.write_text(code_content, encoding="utf-8")
            line_count = len(code_content.splitlines())
            return f"Đã ghi file thành công: {file_path.resolve()} ({line_count} dòng)"
        except OSError as e:
            return f"Lỗi ghi file {file_path}: {e}"

    # ──────────────────────────────────────────────
    # Tool 2: read_python_file
    # ──────────────────────────────────────────────

    def read_python_file(self, filename: str) -> str:
        """Đọc toàn bộ nội dung file Python trong thư mục generated_checks/.
        Trả về code kèm số dòng để dễ tham chiếu khi fix bug.

        Args:
            filename: Tên file (VD: "check_rule_R001.py").

        Returns:
            Nội dung file với số dòng (format: "  1 | code..."), hoặc thông báo lỗi.
        """
        file_path = self._safe_path(filename)

        if not file_path.exists():
            return f"File không tồn tại: {file_path}"

        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            numbered = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
            return f"File: {file_path.name} ({len(lines)} dòng)\n" + "\n".join(numbered)
        except OSError as e:
            return f"Lỗi đọc file {file_path}: {e}"

    # ──────────────────────────────────────────────
    # Tool 3: read_error_traceback
    # ──────────────────────────────────────────────

    def read_error_traceback(self, stderr_text: str) -> str:
        """Phân tích chuỗi error traceback từ stderr.
        Trích xuất error type, message, dòng lỗi, và context xung quanh.

        Dùng khi Agent 4 cần hiểu code bị lỗi gì trước khi fix.

        Args:
            stderr_text: Nội dung stderr từ sandbox execution.

        Returns:
            JSON phân tích gồm: error_type, error_message, line_number, file_name, context_lines.
        """
        if not stderr_text or not stderr_text.strip():
            return json.dumps({"error_type": "None", "message": "stderr rỗng — code chạy OK."})

        result = {
            "error_type": "Unknown",
            "error_message": stderr_text.strip()[-500:],
            "line_number": None,
            "file_name": None,
            "context_lines": [],
        }

        # Tìm error type (dòng cuối thường là "ErrorType: message")
        lines = stderr_text.strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            # Match pattern: "SomeError: some message"
            match = re.match(r"^(\w*Error|\w*Exception):\s*(.+)$", line)
            if match:
                result["error_type"] = match.group(1)
                result["error_message"] = match.group(2)
                break
            # Match SyntaxError (đôi khi không có ":")
            if line.startswith("SyntaxError"):
                result["error_type"] = "SyntaxError"
                result["error_message"] = line
                break

        # Tìm line number từ traceback
        for line in lines:
            match = re.search(r'File "(.+?)", line (\d+)', line)
            if match:
                result["file_name"] = match.group(1)
                result["line_number"] = int(match.group(2))

        # Lấy context lines (các dòng code trong traceback)
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("File ") and not stripped.startswith("Traceback"):
                if not re.match(r"^\w*(Error|Exception)", stripped):
                    result["context_lines"].append(stripped)

        result["context_lines"] = result["context_lines"][-5:]  # Giữ 5 dòng cuối

        return json.dumps(result, indent=2, ensure_ascii=False)

    # ──────────────────────────────────────────────
    # Tool 4: patch_python_file
    # ──────────────────────────────────────────────

    def patch_python_file(self, filename: str, new_code_content: str) -> str:
        """Ghi đè file Python với bản code đã sửa lỗi.
        File phải đã tồn tại (chỉ dùng để patch, không tạo mới — dùng write_python_file để tạo mới).

        Dùng khi Agent 4 đã fix xong bug và cần lưu bản sửa.

        Args:
            filename: Tên file cần patch (VD: "check_rule_R001.py").
            new_code_content: Toàn bộ nội dung code mới (KHÔNG phải diff — ghi đè hoàn toàn).

        Returns:
            Thông báo thành công kèm đường dẫn, hoặc thông báo lỗi.
        """
        file_path = self._safe_path(filename)

        if not file_path.exists():
            return f"File không tồn tại: {file_path}. Dùng write_python_file để tạo mới."

        # Syntax check trước khi ghi — bắt lỗi sớm
        try:
            ast.parse(new_code_content)
        except SyntaxError as e:
            return (
                f"SYNTAX ERROR — code không hợp lệ, KHÔNG patch file.\n"
                f"  Line {e.lineno}: {e.msg}\n"
                f"  {e.text.strip() if e.text else ''}\n"
                f"Sửa lỗi syntax rồi gọi lại patch_python_file()."
            )

        try:
            old_content = file_path.read_text(encoding="utf-8")
            old_lines = len(old_content.splitlines())

            file_path.write_text(new_code_content, encoding="utf-8")
            new_lines = len(new_code_content.splitlines())

            return (
                f"Đã patch file: {file_path.resolve()}\n"
                f"Trước: {old_lines} dòng → Sau: {new_lines} dòng"
            )
        except OSError as e:
            return f"Lỗi patch file {file_path}: {e}"

    # ──────────────────────────────────────────────
    # Tool 5: rewrite_advanced_code
    # ──────────────────────────────────────────────

    def rewrite_advanced_code(self, filename: str, new_code_content: str, reason: str) -> str:
        """Viết lại file code với logic XPath/check mới hoàn toàn.
        Khác với patch_python_file: tool này dùng khi logic CŨ SAI HOÀN TOÀN (không phải bug nhỏ).

        Dùng khi Agent 5 phát hiện nguyên nhân gốc rễ (VD: cần dùng MaskType thay vì BlockType)
        và cần viết lại toàn bộ approach.

        Args:
            filename: Tên file cần rewrite (VD: "check_rule_R001.py").
            new_code_content: Toàn bộ code mới.
            reason: Lý do rewrite (VD: "Block dùng MaskType thay vì BlockType, cần XPath mới").

        Returns:
            Thông báo thành công kèm đường dẫn và lý do.
        """
        file_path = self._safe_path(filename)

        # Syntax check trước khi ghi — bắt lỗi sớm
        try:
            ast.parse(new_code_content)
        except SyntaxError as e:
            return (
                f"SYNTAX ERROR — code không hợp lệ, KHÔNG rewrite file.\n"
                f"  Line {e.lineno}: {e.msg}\n"
                f"  {e.text.strip() if e.text else ''}\n"
                f"Sửa lỗi syntax rồi gọi lại rewrite_advanced_code()."
            )

        try:
            file_path.write_text(new_code_content, encoding="utf-8")
            line_count = len(new_code_content.splitlines())
            return (
                f"Đã rewrite file: {file_path.resolve()} ({line_count} dòng)\n"
                f"Lý do: {reason}"
            )
        except OSError as e:
            return f"Lỗi rewrite file {file_path}: {e}"
