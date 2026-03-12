"""
Schemas cho generated code.
  - GeneratedCode: output của Agent 2 / 4 / 5
"""

from pydantic import BaseModel, Field


class GeneratedCode(BaseModel):
    """File Python check rule đã được sinh ra."""
    rule_id: str
    file_path: str   # VD: "generated_checks/check_rule_R001.py"
    generation_note: str  # "first_gen" | "patched: fixed NoneType" | "rewritten: new XPath"
