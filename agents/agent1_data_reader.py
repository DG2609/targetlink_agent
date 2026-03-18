"""
Agent 1: Data Reader & Search Engine
Skill: skills/data-reader/SKILL.md
"""

from agno.agent import Agent

from tools.search_tools import SearchToolkit
from schemas.block_schemas import BlockMappingData
from utils.skill_loader import load_skill
from utils.model_factory import create_model


def create_agent1(blocks_json_path: str) -> Agent:
    return Agent(
        name="Data Reader",
        role="Tra cứu từ điển block và phân tích vị trí config",
        model=create_model(small=True),
        tools=[SearchToolkit(blocks_json_path=blocks_json_path)],
        instructions=load_skill("data-reader"),
        output_schema=BlockMappingData,
        structured_outputs=True,
    )
