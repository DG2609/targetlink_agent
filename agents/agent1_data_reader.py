"""
Agent 1: Data Reader & Search Engine
Skill: skills/data-reader/SKILL.md
"""

from agno.agent import Agent
from agno.models.google import Gemini

from config import settings
from tools.search_tools import SearchToolkit
from schemas.block_schemas import BlockMappingData
from utils.skill_loader import load_skill


def create_agent1(blocks_json_path: str) -> Agent:
    return Agent(
        name="Data Reader",
        role="Tra cứu từ điển block và phân tích vị trí config",
        model=Gemini(
            id=settings.GEMINI_MODEL,
            vertexai=True,
            project_id=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        ),
        tools=[SearchToolkit(blocks_json_path=blocks_json_path)],
        instructions=load_skill("data-reader"),
        response_model=BlockMappingData,
        structured_outputs=True,
    )
