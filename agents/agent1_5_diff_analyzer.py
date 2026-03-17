"""
Agent 1.5: Diff Analyzer
Skill: skills/diff-analyzer/SKILL.md

Phân tích raw diff giữa 2 model versions → output ConfigDiscovery (structured).
Chạy giữa Agent 1 (Data Reader) và Agent 2 (Code Generator).
Chỉ chạy khi user cung cấp --model-before.
"""

from agno.agent import Agent
from agno.models.google import Gemini

from config import settings
from schemas.diff_schemas import ConfigDiscovery
from utils.skill_loader import load_skill


def create_agent1_5() -> Agent:
    """Tạo Agent 1.5 — Diff Analyzer.

    Không cần tools — chỉ phân tích text input (raw diff + block info)
    và output ConfigDiscovery structured object.
    """
    return Agent(
        name="Diff Analyzer",
        role="Chuyên gia phân tích model diff → xác định config locations chính xác",
        model=Gemini(
            id=settings.GEMINI_MODEL,
            vertexai=True,
            project_id=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        ),
        instructions=load_skill("diff-analyzer"),
        output_schema=ConfigDiscovery,
        structured_outputs=True,
    )
