"""
Agent 3: Validator
Pure Python — không dùng LLM.
Chạy generated code trên từng test case model, so sánh stdout với expected.
Có static code checks trước khi chạy subprocess (bắt lỗi sớm).
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from schemas.validation_schemas import TestCase, ValidationResult, ValidationStatus
from utils.slx_extractor import extract_slx

# Patterns nguy hiểm không được phép trong generated code
_DANGEROUS_PATTERNS = [
    (r'\bos\.system\s*\(', "os.system() — dùng subprocess thay vì os.system"),
    (r'\beval\s*\(', "eval() — không được dùng eval trong generated code"),
    (r'\bexec\s*\(', "exec() — không được dùng exec trong generated code"),
    (r'\b__import__\s*\(', "__import__() — không được dùng dynamic import"),
    (r'\bopen\s*\(.+["\'][wa]', "open() write/append mode — code chỉ được READ model"),
]


def _static_check(code_content: str) -> list[str]:
    """Static checks trước khi chạy code. Trả về list lỗi (rỗng = OK).

    Items bắt đầu bằng 'WARNING:' là non-blocking — chỉ log, không fail.
    """
    errors: list[str] = []

    # Check 1: Phải có main() hoặc check_rule() function
    has_main_func = bool(re.search(r'def\s+(main|check_rule)\s*\(', code_content))
    if not has_main_func:
        errors.append("Thiếu function main() hoặc check_rule() — code phải có entry point function")

    # Check 2: Phải có sys.argv[1] (nhận model_dir)
    has_argv = "sys.argv" in code_content
    if not has_argv:
        errors.append("Thiếu sys.argv[1] — code phải nhận model_dir qua command line argument")

    # Check 3: Phải có json.dumps (output JSON)
    has_json_output = "json.dumps" in code_content
    if not has_json_output:
        errors.append("Thiếu json.dumps — code phải output JSON ra stdout")

    # Check 4: Không có patterns nguy hiểm
    for pattern, description in _DANGEROUS_PATTERNS:
        if re.search(pattern, code_content):
            errors.append(f"Code chứa pattern nguy hiểm: {description}")

    # Check 5 (warning): Nên dùng block_finder thay vì hardcode xpath
    uses_block_finder = "block_finder" in code_content
    uses_hardcoded_xpath = bool(re.search(r"Block\[@BlockType=", code_content))
    if uses_hardcoded_xpath and not uses_block_finder:
        # Warning, không blocking — nhưng log để Agent 5 biết nếu cần fix
        errors.append(
            "WARNING: Code dùng hardcoded BlockType xpath thay vì import block_finder. "
            "Có thể miss Reference/MaskType blocks. "
            "Nên dùng: from utils.block_finder import find_blocks"
        )

    return errors


class Validator:
    """Agent 3: Validator — chạy code sandbox và đối chiếu kết quả.

    Pure Python, không LLM. Static checks → chạy code → so sánh kết quả.
    """

    name = "Validator"

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def validate(
        self, code_file: str, test_cases: list[TestCase], rule_id: str,
    ) -> ValidationResult:
        """Chạy code trên TOÀN BỘ test cases, trả về ValidationResult.

        Chạy hết tất cả test cases (không dừng sớm) để đếm pass/fail chính xác.
        CODE_ERROR dừng ngay (code hỏng thì không chạy tiếp được).
        WRONG_RESULT tiếp tục chạy → PARTIAL_PASS nếu có cả pass lẫn fail.
        """
        total = len(test_cases)

        if not test_cases:
            return ValidationResult(
                rule_id=rule_id,
                status=ValidationStatus.CODE_ERROR,
                stderr="Không có test case nào cho rule này.",
                code_file_path=code_file,
                test_cases_total=0,
            )

        if not Path(code_file).exists():
            return ValidationResult(
                rule_id=rule_id,
                status=ValidationStatus.CODE_ERROR,
                stderr=f"File không tồn tại: {code_file}",
                code_file_path=code_file,
                test_cases_total=total,
            )

        # Static check trước khi chạy subprocess
        try:
            code_content = Path(code_file).read_text(encoding="utf-8")
        except Exception as e:
            return ValidationResult(
                rule_id=rule_id,
                status=ValidationStatus.CODE_ERROR,
                stderr=f"Không đọc được file: {e}",
                code_file_path=code_file,
                test_cases_total=total,
            )

        static_messages = _static_check(code_content)
        static_errors = [m for m in static_messages if not m.startswith("WARNING:")]
        static_warnings = [m for m in static_messages if m.startswith("WARNING:")]
        if static_errors:
            return ValidationResult(
                rule_id=rule_id,
                status=ValidationStatus.CODE_ERROR,
                stderr=f"Static check failed:\n" + "\n".join(f"  - {e}" for e in static_errors),
                code_file_path=code_file,
                test_cases_total=total,
            )

        passed = 0
        first_fail_tc: str | None = None
        first_fail_stdout: str | None = None
        first_fail_actual: dict | None = None
        first_fail_expected: dict | None = None
        first_fail_details: dict | None = None

        for i, tc in enumerate(test_cases):
            # Extract model .slx → thư mục XML
            try:
                model_dir = extract_slx(tc.model_path)
            except (FileNotFoundError, ValueError) as e:
                # CODE_ERROR dừng ngay — code không chạy được
                return ValidationResult(
                    rule_id=rule_id,
                    status=ValidationStatus.CODE_ERROR,
                    stderr=f"Lỗi extract model test case [{i}] {tc.model_path}: {e}",
                    code_file_path=code_file,
                    failed_test_case=tc.model_path,
                    test_cases_passed=passed,
                    test_cases_total=total,
                )

            # Chạy code trong subprocess
            exec_result = self._execute(code_file, model_dir)

            if exec_result["exit_code"] != 0:
                # CODE_ERROR dừng ngay — code hỏng thì chạy tiếp vô nghĩa
                return ValidationResult(
                    rule_id=rule_id,
                    status=ValidationStatus.CODE_ERROR,
                    stdout=exec_result["stdout"],
                    stderr=exec_result["stderr"],
                    code_file_path=code_file,
                    failed_test_case=tc.model_path,
                    test_cases_passed=passed,
                    test_cases_total=total,
                )

            # So sánh stdout với expected
            comparison = self._compare(exec_result["stdout"], tc)

            if comparison["match"]:
                passed += 1
            else:
                # Ghi nhận lỗi đầu tiên (context cho agent retry)
                if first_fail_tc is None:
                    first_fail_tc = tc.model_path
                    first_fail_stdout = exec_result["stdout"]
                    first_fail_actual = comparison["actual_summary"]
                    first_fail_expected = comparison["expected_summary"]
                    first_fail_details = comparison.get("actual_details")

        # Quyết định status
        if passed == total:
            status = ValidationStatus.PASS
        elif passed > 0:
            status = ValidationStatus.PARTIAL_PASS
        else:
            status = ValidationStatus.WRONG_RESULT

        return ValidationResult(
            rule_id=rule_id,
            status=status,
            stdout=first_fail_stdout,
            actual_result=first_fail_actual,
            expected_result=first_fail_expected,
            code_file_path=code_file,
            failed_test_case=first_fail_tc,
            test_cases_passed=passed,
            test_cases_total=total,
            actual_details=first_fail_details,
        )

    # ──────────────────────────────────────────────
    # Internal methods
    # ──────────────────────────────────────────────

    def _execute(self, code_file: str, model_dir: str) -> dict:
        """Chạy file Python trong subprocess cách ly (sandbox)."""
        file_path = Path(code_file)
        try:
            result = subprocess.run(
                [sys.executable, str(file_path.resolve()), model_dir],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(file_path.parent),
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout[-5000:] if len(result.stdout) > 5000 else result.stdout,
                "stderr": result.stderr[-3000:] if len(result.stderr) > 3000 else result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"TIMEOUT: Code chạy quá {self.timeout} giây, đã bị kill.",
            }
        except OSError as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"OS Error: {e}",
            }

    def _compare(self, stdout: str, test_case: TestCase) -> dict:
        """So sánh stdout (JSON) với expected từ test case."""
        try:
            actual = json.loads(stdout)
        except (json.JSONDecodeError, TypeError) as e:
            return {
                "match": False,
                "error": f"Không parse được stdout JSON: {e}",
                "actual_summary": {"raw": stdout[:500]},
                "expected_summary": {
                    "total_blocks": test_case.expected_total_blocks,
                    "pass": test_case.expected_pass,
                    "fail": test_case.expected_fail,
                },
            }

        fields = [
            ("total_blocks", test_case.expected_total_blocks),
            ("pass_count", test_case.expected_pass),
            ("fail_count", test_case.expected_fail),
        ]

        differences = []
        for actual_key, expected_val in fields:
            actual_val = actual.get(actual_key)
            if actual_val != expected_val:
                differences.append({
                    "field": actual_key,
                    "actual": actual_val,
                    "expected": expected_val,
                })

        # Extract block names từ details (nếu có) — giúp Agent 5 diagnose
        actual_details = None
        details = actual.get("details")
        if isinstance(details, dict):
            pass_names = [
                b.get("block_name", "?")
                for b in (details.get("pass") or [])[:10]
            ]
            fail_names = [
                b.get("block_name", "?")
                for b in (details.get("fail") or [])[:10]
            ]
            actual_details = {
                "pass_block_names": pass_names,
                "fail_block_names": fail_names,
            }

        return {
            "match": len(differences) == 0,
            "differences": differences,
            "actual_summary": {
                "total_blocks": actual.get("total_blocks"),
                "pass_count": actual.get("pass_count"),
                "fail_count": actual.get("fail_count"),
            },
            "expected_summary": {
                "total_blocks": test_case.expected_total_blocks,
                "pass": test_case.expected_pass,
                "fail": test_case.expected_fail,
            },
            "actual_details": actual_details,
        }


def create_agent3(timeout: int = 30) -> Validator:
    """Factory function — giữ interface đồng bộ với các agent khác."""
    return Validator(timeout=timeout)
