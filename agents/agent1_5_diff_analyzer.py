"""
Agent 1.5: Diff Analyzer (DEPRECATED)
Skill: skills/diff-analyzer/SKILL.md

DEPRECATED: Replaced by pure Python implementation in pipeline/diff_analyzer.py.
This file is kept for backward compatibility but is NOT used by the pipeline.

Phân tích raw diff giữa 2 model versions → output ConfigDiscovery (structured).
Chạy giữa Agent 1 (Data Reader) và Agent 2 (Code Generator).
Chỉ chạy khi user cung cấp --model-before.
"""

from agno.agent import Agent

from schemas.diff_schemas import ConfigDiscovery
from utils.skill_loader import load_skill
from utils.model_factory import create_model
from utils.schema_utils import gemini_safe_schema


def create_agent1_5() -> Agent:
    """Tạo Agent 1.5 — Diff Analyzer.

    Không cần tools — chỉ phân tích text input (raw diff + block info)
    và output ConfigDiscovery structured object.
    """
    return Agent(
        name="Diff Analyzer",
        role="Chuyên gia phân tích model diff → xác định config locations chính xác",
        model=create_model(small=True),
        instructions=load_skill("diff-analyzer"),
        output_schema=gemini_safe_schema(ConfigDiscovery),
        structured_outputs=True,
        tool_call_limit=5,
    )
