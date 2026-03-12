"""
Agent 5: Model Inspector (Copilot 2)
Skill: skills/model-inspector/SKILL.md
"""

from agno.agent import Agent
from agno.models.google import Gemini

from config import settings
from tools.xml_tools import XmlToolkit
from tools.code_tools import CodeToolkit
from utils.skill_loader import load_skill


def create_agent5(model_dir: str) -> Agent:
    return Agent(
        name="Model Inspector",
        role="Data Detective điều tra XML tree tìm nguyên nhân kết quả sai",
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
        instructions=load_skill("model-inspector"),
        markdown=True,
        show_tool_calls=True,
    )
