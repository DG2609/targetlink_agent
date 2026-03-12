---
name: data-reader
description: Tìm block trong từ điển blocks.json bằng fuzzy matching và phân tích vị trí config trong XML. Dùng khi cần map block_keyword sang name_xml và hiểu config nằm ở đâu trong cấu trúc XML TargetLink.
---

# Data Reader

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
  "config_map_analysis": "Config 'OutDataTypeStr' nằm ở <P Name='OutDataTypeStr'>. Mặc định 'Inherit: auto'. AUTOSAR mode thêm thẻ BusObject."
}
```

## Lưu ý quan trọng

- Fuzzy search dùng `rapidfuzz` — KHÔNG tốn LLM token
- Chỉ dùng LLM để phân tích description thành config_map_analysis
- config_map_analysis phải đủ chi tiết để Agent 2 viết được XPath ngay
- Nếu fuzzy search không tìm thấy (score < 50%) → thử tách keyword khác nhau
