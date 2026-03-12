"""
Agent 0: Rule Analyzer
Skill: skills/rule-analyzer/SKILL.md
"""

from agno.agent import Agent
from agno.models.google import Gemini

from config import settings
from schemas.rule_schemas import ParsedRule
from utils.skill_loader import load_skill


def create_agent0() -> Agent:
    return Agent(
        name="Rule Analyzer",
        role="Phân tích luật ngôn ngữ tự nhiên thành dữ liệu cấu trúc",
        model=Gemini(
            id=settings.GEMINI_MODEL,
            vertexai=True,
            project_id=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        ),
        instructions=load_skill("rule-analyzer"),
        response_model=ParsedRule,
        structured_outputs=True,
    )
