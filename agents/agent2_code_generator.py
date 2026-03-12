"""
Agent 2: Code Generator (Copilot 1)
Skill: skills/code-generator/SKILL.md
"""

from agno.agent import Agent
from agno.models.google import Gemini

from config import settings
from tools.xml_tools import XmlToolkit
from tools.code_tools import CodeToolkit
from utils.skill_loader import load_skill


def create_agent2(model_dir: str) -> Agent:
    return Agent(
        name="Code Generator",
        role="Senior Python Developer viết rule checking scripts",
        model=Gemini(
            id=settings.GEMINI_MODEL,
            vertexai=True,
            project_id=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        ),
        tools=[
            XmlToolkit(model_dir=model_dir),
            CodeToolkit(output_dir=str(settings.GENERATED_CHECKS_DIR)),
        ],
        instructions=load_skill("code-generator"),
        markdown=True,
        show_tool_calls=True,
    )
