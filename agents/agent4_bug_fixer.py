"""
Agent 4: Bug Fixer
Skill: skills/bug-fixer/SKILL.md
"""

from agno.agent import Agent

from config import settings
from tools.code_tools import CodeToolkit
from utils.skill_loader import load_skill
from utils.model_factory import create_model


def create_agent4() -> Agent:
    return Agent(
        name="Bug Fixer",
        role="Kỹ sư sửa lỗi code dựa trên error traceback",
        model=create_model(),
        tools=[CodeToolkit(output_dir=str(settings.GENERATED_CHECKS_DIR))],
        instructions=load_skill("bug-fixer"),
        markdown=True,
        debug_mode=True,
        # 10 calls: reads code (~2), fixes (~1-2 rewrites), no XML exploration needed. Lower than Agent 2/5.
        tool_call_limit=10,
    )
