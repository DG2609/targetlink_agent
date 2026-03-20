"""
Schemas cho test_config.json — consolidated input format.

Thay vì cung cấp 4 file riêng (model, blocks, rules, expected),
user cung cấp 1 file test_config.json chứa tất cả.
"""

from typing import Optional

from pydantic import BaseModel, Field


class TestConfigTestCase(BaseModel):
    """1 test case trong test_config.json."""

    model_path: str = Field(description="Path tới .slx model file")
    expected_total_blocks: int = Field(description="Số blocks mong đợi")
    expected_pass: int = Field(description="Số blocks pass mong đợi")
    expected_fail: int = Field(description="Số blocks fail mong đợi")


class TestConfigRule(BaseModel):
    """1 rule trong test_config.json."""

    rule_id: str = Field(description="ID rule, VD: 'R001'")
    description: str = Field(description="Mô tả rule bằng ngôn ngữ tự nhiên")
    test_cases: list[TestConfigTestCase] = Field(
        default_factory=list,
        description="Danh sách test cases cho rule này",
    )


class TestConfig(BaseModel):
    """Top-level test_config.json schema.

    Example:
        {
            "blocks_path": "data/blocks.json",
            "model_before": null,
            "rules": [
                {
                    "rule_id": "R001",
                    "description": "All Gain blocks must have SaturateOnIntegerOverflow equal to 'on'",
                    "test_cases": [
                        {
                            "model_path": "data/model4_CcodeGeneration.slx",
                            "expected_total_blocks": 19,
                            "expected_pass": 18,
                            "expected_fail": 1
                        }
                    ]
                }
            ]
        }
    """

    blocks_path: str = Field(
        default="data/blocks.json",
        description="Path tới blocks.json (từ điển block)",
    )
    model_before: Optional[str] = Field(
        default=None,
        description="Path model TRƯỚC khi sửa config (dùng cho diff-based discovery)",
    )
    rules: list[TestConfigRule] = Field(
        description="Danh sách rules cần check",
    )
