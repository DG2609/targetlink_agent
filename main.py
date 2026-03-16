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
Ví dụ:
  python main.py --model data/model.slx --blocks data/blocks.json \\
                 --rules data/rules.json --expected data/expected_results.json
        """,
    )
    parser.add_argument("--model",    required=True, help="File model TargetLink (.slx)")
    parser.add_argument("--blocks",   required=True, help="Từ điển block (blocks.json)")
    parser.add_argument("--rules",    required=True, help="Luật cần kiểm tra (rules.json)")
    parser.add_argument("--expected", required=True, help="Test case kết quả mong đợi")
    parser.add_argument("--output",   default=None,  help="File output báo cáo JSON (tuỳ chọn)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    # Import sau khi logger setup để tránh import log noise
    from pipeline.runner import run_pipeline
    from config import settings

    # Validate input files tồn tại
    for label, path in [
        ("--model", args.model),
        ("--blocks", args.blocks),
        ("--rules", args.rules),
        ("--expected", args.expected),
    ]:
        if not Path(path).exists():
            print(f"[ERROR] File không tồn tại ({label}): {path}", file=sys.stderr)
            return 1

    report = await run_pipeline(
        model_path=args.model,
        blocks_path=args.blocks,
        rules_path=args.rules,
        expected_path=args.expected,
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
