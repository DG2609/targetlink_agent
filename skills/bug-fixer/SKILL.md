---
name: bug-fixer
description: Sửa lỗi code do AI sinh ra dựa trên error traceback. Đọc stderr, phân tích nguyên nhân, patch code. Dùng khi Agent 3 phát hiện CODE_ERROR (Syntax/Runtime error). Tối đa 3 lần retry.
---

# Bug Fixer

Đọc lỗi, hiểu nguyên nhân, sửa code.

## Tools được cấp

- `read_error_traceback(stderr_text)` — phân tích error → type, message, line number
- `read_python_file(filename)` — đọc code kèm line numbers
- `patch_python_file(filename, new_code_content)` — ghi đè file đã sửa

## Quy trình

**Bước 1**: Phân tích lỗi
```
read_error_traceback(stderr)
```

**Bước 2**: Đọc code bị lỗi
```
read_python_file("check_rule_R001.py")
```

**Bước 3**: Sửa theo pattern

| Error type | Nguyên nhân thường gặp | Cách fix |
|---|---|---|
| `AttributeError: 'NoneType' has no attribute 'text'` | XML node trả về None | `value = node.text if node is not None else "NOT_FOUND"` |
| `IndexError: list index out of range` | XPath trả về list rỗng | `if len(nodes) > 0:` |
| `XPathError` | Sai cú pháp XPath | Sửa quotes, brackets, escape |
| `SyntaxError` | Lỗi Python cơ bản | Sửa trực tiếp |
| `FileNotFoundError` | Path sai | Kiểm tra sys.argv[1] |

**Bước 4**: Lưu bản sửa
```
patch_python_file("check_rule_R001.py", fixed_code)
```

## Nguyên tắc

- Chỉ sửa phần bị lỗi, **giữ nguyên logic tổng thể**
- KHÔNG thay đổi tên hàm `check_rule` hay format output
- KHÔNG thay đổi cách nhận argument `sys.argv[1]`
- Nếu không rõ nguyên nhân → bọc thêm try/except rộng hơn
- Mỗi lần patch ghi rõ đã sửa gì trong generation_note
