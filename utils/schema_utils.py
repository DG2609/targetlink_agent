"""
Utility để làm sạch Pydantic schema trước khi gửi lên Gemini.

Gemini API không hỗ trợ keyword "examples" trong JSON Schema.
Thay vì xoá examples khỏi schema gốc (mất documentation),
ta tạo proxy class dynamic — giữ nguyên schema gốc, chỉ strip khi serialize.

Usage:
    from utils.schema_utils import gemini_safe_schema

    agent = Agent(
        output_schema=gemini_safe_schema(ParsedRule),
        structured_outputs=True,
    )
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def _strip_examples(obj: Any) -> Any:
    """Recursively strip 'examples' key from JSON schema dict."""
    if isinstance(obj, dict):
        return {
            k: _strip_examples(v)
            for k, v in obj.items()
            if k != "examples"
        }
    if isinstance(obj, list):
        return [_strip_examples(item) for item in obj]
    return obj


def gemini_safe_schema(model_cls: type[BaseModel]) -> type[BaseModel]:
    """Tạo proxy class giữ nguyên behavior nhưng strip examples khỏi JSON schema.

    Schema gốc không bị sửa — examples vẫn tồn tại cho documentation.
    Chỉ output của model_json_schema() được clean trước khi gửi lên Gemini.
    """

    class _SafeSchema(model_cls):  # type: ignore[valid-type]
        @classmethod
        def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raw = super().model_json_schema(*args, **kwargs)
            return _strip_examples(raw)

    # Giữ tên + module gốc để Agno/Pydantic serialize đúng
    _SafeSchema.__name__ = model_cls.__name__
    _SafeSchema.__qualname__ = model_cls.__qualname__
    _SafeSchema.__module__ = model_cls.__module__

    return _SafeSchema
