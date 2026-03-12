---
name: rule-analyzer
description: Phân tích mô tả luật TargetLink bằng ngôn ngữ tự nhiên (Việt/Anh) thành dữ liệu cấu trúc. Dùng khi cần bóc tách rule text thành block_keyword, config_name, condition, expected_value.
---

# Rule Analyzer

Đọc text mô tả luật và trích xuất thành JSON cấu trúc.

## Quy trình

1. Đọc mô tả luật (tiếng Việt hoặc tiếng Anh)
2. Xác định block cần kiểm tra
3. Xác định config/property cần check
4. Xác định loại điều kiện và giá trị so sánh
5. Trả về JSON theo đúng schema

## Output Schema

```json
{
  "rule_id": "R001",
  "block_keyword": "inport",
  "rule_alias": "inport(targetlink)",
  "config_name": "DataType",
  "condition": "not_equal",
  "expected_value": "Inherit: auto"
}
```

## Hướng dẫn chọn condition

| Mô tả trong rule text | condition | expected_value |
|---|---|---|
| "phải set cụ thể / không được để Inherited" | `not_equal` | giá trị mặc định bị cấm |
| "phải bằng X" | `equal` | `X` |
| "không được để trống / phải có giá trị" | `not_empty` | `""` |
| "phải chứa X" | `contains` | `X` |
| "phải là 1 trong [A, B, C]" | `in_list` | `A,B,C` |

## Ví dụ

**Input**: "Tất cả inport(targetlink) phải set DataType cụ thể, không được để Inherited"

**Output**:
```json
{
  "block_keyword": "inport",
  "rule_alias": "inport(targetlink)",
  "config_name": "DataType",
  "condition": "not_equal",
  "expected_value": "Inherit: auto"
}
```

**Input**: "Main TargetLink Data block phải set CodeGenerateMode = 0"

**Output**:
```json
{
  "block_keyword": "main data",
  "rule_alias": "Main TargetLink Data",
  "config_name": "CodeGenerateMode",
  "condition": "equal",
  "expected_value": "0"
}
```

## Lưu ý

- Chỉ trả về JSON, không giải thích thêm
- block_keyword luôn viết thường
- Nếu rule text không rõ condition → mặc định dùng `not_equal`
