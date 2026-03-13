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


def create_agent2(xml_toolkit: XmlToolkit, output_dir: str) -> Agent:
    """Tạo Agent 2 với shared XmlToolkit (chia sẻ cache với Agent 5).

    Args:
        xml_toolkit: Instance XmlToolkit đã khởi tạo (shared cache).
        output_dir: Thư mục output cho generated code.
    """
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
            xml_toolkit,
            CodeToolkit(output_dir=output_dir),
        ],
        instructions=load_skill("code-generator"),
        markdown=True,
        debug_mode=True,
        tool_call_limit=15,
    )
