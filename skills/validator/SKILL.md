---
name: validator
description: Chạy code check rule trong sandbox (subprocess cách ly), rồi so sánh kết quả với test case expected. Dùng khi cần validate code do Agent 2/4/5 sinh ra — trả về PASS, CODE_ERROR, hoặc WRONG_RESULT.
---

# Validator

Chạy code sandbox và đánh giá kết quả.

## Tools được cấp

- `sandbox_execute_python(file_path)` — chạy file .py trong subprocess (timeout 30s)
- `compare_json_result(actual_json, expected_json)` — so sánh kết quả

## Quy trình

**Bước 1**: Chạy code
```
sandbox_execute_python("generated_checks/check_rule_R001.py")
```

**Bước 2**: Kiểm tra kết quả
```
Nếu exit_code != 0 hoặc stderr không rỗng:
  → status = CODE_ERROR
  → Chuyển cho Agent 4 (Bug Fixer)

Nếu exit_code == 0 và stderr rỗng:
  → Parse stdout thành JSON
  → Tiếp bước 3
```

**Bước 3**: So sánh với expected
```
compare_json_result(stdout, expected_json)
```
```
Nếu match = true:
  → status = PASS ✅

Nếu match = false:
  → status = WRONG_RESULT
  → Chuyển cho Agent 5 (Inspector)
```

## Output Schema

```json
{
  "rule_id": "R001",
  "status": "PASS | CODE_ERROR | WRONG_RESULT",
  "stdout": "...",
  "stderr": "...",
  "actual_result": {},
  "expected_result": {},
  "code_file_path": "generated_checks/check_rule_R001.py"
}
```

## Bảng quyết định routing

| status | Hành động | Agent tiếp theo |
|--------|----------|-----------------|
| PASS | Ghi report, chuyển rule tiếp | Không |
| CODE_ERROR | Gửi stderr + file path | Agent 4 (max 3 retries) |
| WRONG_RESULT | Gửi actual vs expected + block info | Agent 5 (max 3 retries) |
