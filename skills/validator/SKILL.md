---
name: validator
description: Agent 3 — pure Python, không LLM. Static check → subprocess chạy generated code trên từng test case model → so sánh stdout JSON với expected. Trả về PASS, PARTIAL_PASS, CODE_ERROR, hoặc WRONG_RESULT. Route đến Agent 4/5 khi fail.
---

# Validator

Chạy code sandbox trên nhiều test case và đánh giá kết quả. **Không dùng LLM.**

## Quy trình

```
for each test_case in rule.test_cases:
    1. extract_slx(test_case.model_path) → model_dir
    2. subprocess.run(code_file, model_dir) → stdout, stderr, exit_code
    3. if exit_code != 0 → CODE_ERROR, dừng ngay (code hỏng)
    4. compare stdout JSON vs expected → ghi nhận pass/fail, TIẾP TỤC chạy
→ Tất cả pass → PASS
→ Có pass + có fail → PARTIAL_PASS
→ Tất cả fail → WRONG_RESULT
```

## Input

- `code_file`: path tới file .py do Agent 2 sinh ra
- `test_cases`: list TestCase, mỗi cái gồm:
  - `model_path`: đường dẫn .slx
  - `expected_total_blocks`: int
  - `expected_pass`: int
  - `expected_fail`: int

## Output: ValidationResult

| Field | Mô tả |
|-------|--------|
| status | PASS / PARTIAL_PASS / CODE_ERROR / WRONG_RESULT |
| stdout | stdout từ test case fail đầu tiên (nếu có) |
| stderr | stderr từ test case fail (nếu có) |
| actual_result | dict {total_blocks, pass_count, fail_count} |
| expected_result | dict {total_blocks, pass_count, fail_count} |
| actual_details | dict {pass_block_names: [...], fail_block_names: [...]} — tên cụ thể từng block pass/fail |
| failed_test_case | model_path của test case fail đầu tiên |
| test_cases_passed | tổng số test case đã pass |
| test_cases_total | tổng số test case |

## Bảng quyết định routing

Routing phân tách rõ 2 loại lỗi vì cách fix hoàn toàn khác nhau:
- **CODE_ERROR** = code crash/syntax → Agent 4 (Bug Fixer) fix mà KHÔNG đổi logic
- **WRONG_RESULT / PARTIAL_PASS** = logic sai → Agent 5 (Inspector) khám phá lại model rồi viết lại

| status | Hành động | Agent tiếp theo |
|--------|----------|-----------------|
| PASS | Ghi report, chuyển rule tiếp | Không |
| CODE_ERROR | Gửi stderr + file path + test case | Agent 4 (max 3 retries) |
| WRONG_RESULT | Gửi actual vs expected + test case | Agent 5 (max 3 retries) |
| PARTIAL_PASS | Code OK nhưng logic sai một số model → agent5 | Agent 5 (max 3 retries) |
