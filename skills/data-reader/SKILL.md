---
name: data-reader
description: "DEPRECATED — replaced by pipeline/data_reader.py (pure Python, no LLM). Kept for reference only."
---

# Data Reader (DEPRECATED)

> **DEPRECATED**: Agent 1 đã được thay thế bằng pure Python implementation tại `pipeline/data_reader.py`.
> File agent declaration `agents/agent1_data_reader.py` cũng đã deprecated.
> Skill này giữ lại làm tài liệu tham khảo — KHÔNG được pipeline sử dụng.

Tra cứu từ điển block và phân tích description để lập bản đồ config.

## Tools được cấp

- `fuzzy_search_json(keyword, top_k)` — tìm block bằng fuzzy matching
- `read_dictionary(name_xml)` — đọc description đầy đủ của block

## Quy trình

1. Nhận `block_keyword` và `config_name` từ Agent 0
2. Dùng `fuzzy_search_json` với block_keyword → lấy top matches
3. Chọn match tốt nhất (score cao nhất, phù hợp ngữ cảnh)
4. Dùng `read_dictionary` với name_xml → đọc description đầy đủ
5. Từ description, phân tích và trả lời:
   - Config cần check nằm ở thẻ XML nào? XPath gợi ý?
   - Config có bị ẩn/thay đổi theo Mode (Standard vs AUTOSAR)?
   - Tên XML có khác tên UI không?

## Output Schema

```json
{
  "name_ui": "Inport",
  "name_xml": "TL_Inport",
  "xml_representation": "masked",
  "search_confidence": 85,
  "source_type_pattern": "",
  "config_map_analysis": "Config 'OutDataTypeStr' nằm ở <P Name='OutDataTypeStr'>. Mặc định 'Inherit: auto'. AUTOSAR mode thêm thẻ BusObject."
}
```

## Các field BẮT BUỘC trong output

- **`xml_representation`**: Dạng block trong XML
  - `"native"` — tìm bằng BlockType trực tiếp (VD: Gain, Abs, Sum)
  - `"reference"` — BlockType="Reference" + SourceType (VD: Compare To Constant)
  - `"masked"` — BlockType="SubSystem" + MaskType (VD: TL_Inport, TL_Gain)
  - `"unknown"` — không rõ → Agent 2 tự khám phá
- **`search_confidence`**: Score từ fuzzy search (0-100). Dưới 70 = Agent 2 cần verify thêm
- **`source_type_pattern`**: SourceType value (chỉ khi xml_representation="reference")

## Cách xác định xml_representation

Từ description trong blocks.json:
- Nếu description nói `<Block BlockType='Gain'>` → `"native"`
- Nếu description nói `MaskType` hoặc `TL_` → `"masked"`
- Nếu description nói `BlockType='Reference'` hoặc `SourceBlock` → `"reference"`
- Nếu không rõ → `"unknown"`

## Trường hợp `block_keyword` rỗng

Khi Agent 0 trả `block_keyword=""` — rule chỉ nói về config, không nói block type nào:
- Trả output với `name_xml=""`, `name_ui=""`, `xml_representation="unknown"`, `search_confidence=0`
- `config_map_analysis` ghi: "Rule không chỉ định block type, Agent 2 cần dùng find_config_locations() để xác định"
- Agent 2 sẽ tự tìm tất cả block types có config này từ model

## Lưu ý quan trọng

- Fuzzy search dùng `rapidfuzz` — KHÔNG tốn LLM token, nên gọi trước khi suy luận
- Chỉ dùng LLM để phân tích description thành config_map_analysis — tiết kiệm token budget
- config_map_analysis phải đủ chi tiết để Agent 2 viết được XPath ngay — đây là thông tin quan trọng nhất Agent 2 cần
- Nếu fuzzy search không tìm thấy (score < 35%) → thử tách keyword khác nhau, hoặc bỏ prefix/suffix
