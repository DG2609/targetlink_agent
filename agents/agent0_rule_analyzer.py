"""
Agent 0: Rule Analyzer
Skill: skills/rule-analyzer/SKILL.md
"""

from agno.agent import Agent

from schemas.rule_schemas import ParsedRule
from utils.skill_loader import load_skill
from utils.model_factory import create_model
from utils.schema_utils import gemini_safe_schema


def create_agent0() -> Agent:
    return Agent(
        name="Rule Analyzer",
        role="Phân tích luật ngôn ngữ tự nhiên thành dữ liệu cấu trúc",
        model=create_model(small=True),
        instructions=load_skill("rule-analyzer"),
        output_schema=gemini_safe_schema(ParsedRule),
        structured_outputs=True,
        tool_call_limit=5,
    )
