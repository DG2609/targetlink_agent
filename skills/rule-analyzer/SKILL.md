---
name: rule-analyzer
description: Agent 0 — phân tích mô tả luật TargetLink bằng ngôn ngữ tự nhiên (Việt/Anh) → JSON cấu trúc. Kích hoạt khi cần bóc tách rule text thành block_keyword, config_name, condition, expected_value.
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
| "không được dùng block X, Y" | `not_equal` | `""` + `target_block_types: ["X", "Y"]` |

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

**Input**: "SaturateOnIntegerOverflow phải bật 'on' trên tất cả blocks"

**Output**:
```json
{
  "block_keyword": "",
  "rule_alias": "all blocks",
  "config_name": "SaturateOnIntegerOverflow",
  "condition": "equal",
  "expected_value": "on"
}
```

**Input**: "Không được dùng block Buffer và Product trong model"

**Output**:
```json
{
  "block_keyword": "",
  "rule_alias": "forbidden blocks",
  "config_name": "",
  "condition": "not_equal",
  "expected_value": "",
  "target_block_types": ["Buffer", "Product"]
}
```

## ParsedRule mở rộng

Ngoài các field cơ bản, ParsedRule còn hỗ trợ:

### compound_logic + additional_configs (rule check nhiều config)

Nếu rule yêu cầu check **nhiều config** trên cùng block:
- `compound_logic`: `"AND"` (tất cả config phải đúng) hoặc `"OR"` (ít nhất 1 đúng)
- `additional_configs`: danh sách config phụ kèm condition + expected_value

**Ví dụ**: "Inport phải set DataType cụ thể VÀ PortDimensions không rỗng"
```json
{
  "block_keyword": "inport",
  "config_name": "OutDataTypeStr",
  "condition": "not_equal",
  "expected_value": "Inherit: auto",
  "compound_logic": "AND",
  "additional_configs": [
    {"config_name": "PortDimensions", "condition": "not_empty", "expected_value": ""}
  ]
}
```

### target_block_types (explicit block list)

Nếu rule nói rõ block types cụ thể (không cần auto-discover):
```json
{
  "target_block_types": ["TL_Inport", "TL_Outport"]
}
```
Rỗng `[]` = mặc định, Agent 2 tự tìm từ `block_keyword`.

### scope + scope_filter (giới hạn phạm vi)

Nếu rule chỉ áp dụng cho 1 phần model:
- `scope`: `"all_instances"` (mặc định), `"specific_path"`, `"subsystem"`
- `scope_filter`: pattern lọc, VD: `"SubSystem1/*"`

Nếu rule không đề cập phạm vi → giữ defaults: `scope="all_instances"`, `scope_filter=""`.

## Lưu ý

- Chỉ trả về JSON, không giải thích thêm — output được parse tự động bằng Pydantic, text thừa gây lỗi
- block_keyword luôn viết thường — Agent 1 dùng fuzzy search case-insensitive
- Nếu rule text không rõ condition → mặc định dùng `not_equal` — đây là trường hợp phổ biến nhất (rule cấm giá trị mặc định)
- **Nếu rule KHÔNG nói rõ block type** (chỉ nói về config) → `block_keyword` = `""` (rỗng). Agent 2 sẽ tự xác định block types từ model bằng `find_config_locations()` — không cần đoán block type
- Ví dụ: "SaturateOnIntegerOverflow phải bật on" → `block_keyword: ""`, `config_name: "SaturateOnIntegerOverflow"`
- Nếu rule đơn giản (1 config, 1 block type, all instances) → KHÔNG cần set compound_logic, target_block_types, scope — giữ defaults
