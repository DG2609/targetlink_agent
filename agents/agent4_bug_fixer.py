"""
Agent 4: Bug Fixer
Skill: skills/bug-fixer/SKILL.md
"""

from agno.agent import Agent
from agno.models.google import Gemini

from config import settings
from tools.code_tools import CodeToolkit
from utils.skill_loader import load_skill


def create_agent4() -> Agent:
    return Agent(
        name="Bug Fixer",
        role="Kỹ sư sửa lỗi code dựa trên error traceback",
        model=Gemini(
            id=settings.GEMINI_MODEL,
            vertexai=True,
            project_id=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        ),
        tools=[CodeToolkit(output_dir=str(settings.GENERATED_CHECKS_DIR))],
        instructions=load_skill("bug-fixer"),
        markdown=True,
        debug_mode=True,
        tool_call_limit=10,
    )
