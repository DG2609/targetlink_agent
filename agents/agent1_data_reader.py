"""
Agent 1: Data Reader & Search Engine (DEPRECATED)
Skill: skills/data-reader/SKILL.md

DEPRECATED: Replaced by pure Python implementation in pipeline/data_reader.py.
This file is kept for backward compatibility but is NOT used by the pipeline.
"""

from pathlib import Path

from agno.agent import Agent

from tools.search_tools import SearchToolkit
from schemas.block_schemas import BlockMappingData
from utils.skill_loader import load_skill
from utils.model_factory import create_model
from utils.schema_utils import gemini_safe_schema


def create_agent1(blocks_json_path: str) -> Agent:
    if not Path(blocks_json_path).exists():
        raise FileNotFoundError(f"blocks.json không tồn tại: {blocks_json_path}")
    return Agent(
        name="Data Reader",
        role="Tra cứu từ điển block và phân tích vị trí config",
        model=create_model(small=True),
        tools=[SearchToolkit(blocks_json_path=blocks_json_path)],
        instructions=load_skill("data-reader"),
        output_schema=gemini_safe_schema(BlockMappingData),
        structured_outputs=True,
        tool_call_limit=5,
    )
