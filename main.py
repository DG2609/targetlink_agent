"""
Entry point duy nhất của hệ thống.
Chỉ parse CLI args, setup logger, và gọi pipeline.
"""

import argparse
import asyncio
import io
import json
import sys
from pathlib import Path

# Force UTF-8 output trên Windows (tránh UnicodeEncodeError với tiếng Việt)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from utils.logger import setup_logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TargetLink Rule Checking System — Multi-Agent AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Cách 1 — Wrapper files (khuyến nghị):
  python main.py --input data/input.json --validate data/validate.json

Cách 2 — Args riêng lẻ:
  python main.py --model data/model.slx --blocks data/blocks.json \\
                 --rules data/rules.json --expected data/expected_results.json

Diff-based discovery:
  python main.py --input data/input.json --validate data/validate.json \\
                 --model-before data/model_before.slx

Chỉ chạy diff:
  python main.py --input data/input.json --validate data/validate.json \\
                 --model-before data/model_before.slx --diff-only

Format input.json:
  {"model": "path/to.slx", "blocks": "path/blocks.json", "rules": "path/rules.json"}

Format validate.json:
  {"expected_results": "path/expected_results.json"}
        """,
    )
    # Cách 1: Wrapper files
    parser.add_argument("--input",    default=None, help="File input bundle (chứa model, blocks, rules)")
    parser.add_argument("--validate", default=None, help="File validation bundle (chứa expected_results)")

    # Cách 2: Args riêng lẻ (backward compatible)
    parser.add_argument("--model",    default=None, help="File model TargetLink (.slx)")
    parser.add_argument("--blocks",   default=None, help="Từ điển block (blocks.json)")
    parser.add_argument("--rules",    default=None, help="Luật cần kiểm tra (rules.json)")
    parser.add_argument("--expected", default=None, help="Test case kết quả mong đợi")

    # Chung
    parser.add_argument("--output",   default=None,  help="File output báo cáo JSON (tuỳ chọn)")
    parser.add_argument("--model-before", default=None,
                        help="Model TRƯỚC khi sửa config (tuỳ chọn, dùng cho diff-based discovery)")
    parser.add_argument("--diff-only", action="store_true",
                        help="Chỉ chạy diff và in kết quả JSON, không chạy pipeline")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


def _resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    """Resolve wrapper files → flat args.

    Nếu --input được cung cấp → đọc file, extract model/blocks/rules.
    Nếu --validate được cung cấp → đọc file, extract expected.
    Args riêng lẻ (--model, --blocks...) override wrapper nếu cả 2 cùng có.
    """
    # ── Resolve --input ──
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"[ERROR] File không tồn tại (--input): {args.input}", file=sys.stderr)
            sys.exit(1)
        try:
            input_data = json.loads(input_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON không hợp lệ (--input): {args.input} — {e}", file=sys.stderr)
            sys.exit(1)

        # Chỉ set nếu chưa có từ args riêng lẻ
        if not args.model:
            args.model = input_data.get("model")
        if not args.blocks:
            args.blocks = input_data.get("blocks")
        if not args.rules:
            args.rules = input_data.get("rules")
        if not args.model_before and input_data.get("model_before"):
            args.model_before = input_data["model_before"]

    # ── Resolve --validate ──
    if args.validate:
        validate_path = Path(args.validate)
        if not validate_path.exists():
            print(f"[ERROR] File không tồn tại (--validate): {args.validate}", file=sys.stderr)
            sys.exit(1)
        try:
            validate_data = json.loads(validate_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON không hợp lệ (--validate): {args.validate} — {e}", file=sys.stderr)
            sys.exit(1)

        if not args.expected:
            args.expected = validate_data.get("expected_results")

    # ── Validate required fields ──
    missing = []
    if not args.model:
        missing.append("model")
    if not args.blocks:
        missing.append("blocks")
    if not args.rules:
        missing.append("rules")
    if not args.expected:
        missing.append("expected")

    if missing:
        print(
            f"[ERROR] Thiếu: {', '.join(missing)}. "
            f"Dùng --input/--validate hoặc --model/--blocks/--rules/--expected.",
            file=sys.stderr,
        )
        sys.exit(1)

    return args


async def main_async(args: argparse.Namespace) -> int:
    # Import sau khi logger setup để tránh import log noise
    from pipeline.runner import run_pipeline
    from config import settings

    # Validate input files tồn tại
    required_files = [
        ("model", args.model),
        ("blocks", args.blocks),
        ("rules", args.rules),
        ("expected", args.expected),
    ]
    if args.model_before:
        required_files.append(("model-before", args.model_before))

    for label, path in required_files:
        if not Path(path).exists():
            print(f"[ERROR] File không tồn tại ({label}): {path}", file=sys.stderr)
            return 1

    # ── Validate --diff-only requires --model-before ──
    if args.diff_only and not args.model_before:
        print("[ERROR] --diff-only yêu cầu --model-before (cần 2 model để so sánh)", file=sys.stderr)
        return 1

    # ── Diff-based discovery (tuỳ chọn) ──
    diff_result = None
    if args.model_before:
        from utils.model_differ import diff_models
        print(f"[INFO] Diff models: {args.model_before} vs {args.model}", file=sys.stderr)
        try:
            diff_result = diff_models(args.model_before, args.model)
        except (FileNotFoundError, ValueError) as e:
            print(f"[ERROR] Diff failed: {e}", file=sys.stderr)
            return 1
        print(
            f"[INFO] Diff complete: {len(diff_result.block_changes)} block changes, "
            f"{len(diff_result.config_changes)} config changes",
            file=sys.stderr,
        )

        if args.diff_only:
            print(diff_result.model_dump_json(indent=2))
            return 0

    report = await run_pipeline(
        model_path=args.model,
        blocks_path=args.blocks,
        rules_path=args.rules,
        expected_path=args.expected,
        diff_result=diff_result,
    )

    # In báo cáo ra stdout
    report_json = report.model_dump_json(indent=2)
    print(report_json)

    # Lưu file nếu có --output
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report_json, encoding="utf-8")
        print(f"\n[INFO] Báo cáo đã lưu: {out.resolve()}", file=sys.stderr)

    # Exit code: 0 nếu tất cả PASS, 1 nếu có rule cần human review
    summary = report.summary

    # ── Human-readable summary table ──
    print("\n" + "=" * 70, file=sys.stderr)
    print(f"  PIPELINE SUMMARY — {summary['total']} rules", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"  {'Rule':<10} {'Status':<22} {'Duration':>10} {'Retries':>8}", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    for r in report.results:
        retries = len(r.pipeline_trace)
        duration = f"{r.rule_duration_seconds:.1f}s" if r.rule_duration_seconds else "—"
        print(f"  {r.rule_id:<10} {r.status.value:<22} {duration:>10} {retries:>8}", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    partial_info = f" | Partial: {summary['partial_pass']}" if summary.get('partial_pass', 0) > 0 else ""
    print(
        f"  Pass: {summary['pass']}/{summary['total']} | "
        f"Failed: {summary['failed']}{partial_info} | "
        f"Total: {report.total_duration_seconds:.1f}s",
        file=sys.stderr,
    )
    print("=" * 70, file=sys.stderr)

    return 1 if summary["failed"] > 0 else 0


def main() -> None:
    args = parse_args()
    args = _resolve_args(args)
    setup_logger(log_level=args.log_level)
    try:
        exit_code = asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n[INFO] Bị ngắt bởi người dùng (Ctrl+C).", file=sys.stderr)
        exit_code = 130
    except Exception as e:
        print(f"\n[FATAL] Pipeline lỗi không xử lý được: {e}", file=sys.stderr)
        exit_code = 2
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
