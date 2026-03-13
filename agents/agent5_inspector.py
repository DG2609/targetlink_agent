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


def create_agent5(xml_toolkit: XmlToolkit, output_dir: str) -> Agent:
    """Tạo Agent 5 với shared XmlToolkit (chia sẻ cache với Agent 2).

    Args:
        xml_toolkit: Instance XmlToolkit đã khởi tạo (shared cache).
        output_dir: Thư mục output cho rewritten code.
    """
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
            xml_toolkit,
            CodeToolkit(output_dir=output_dir),
        ],
        instructions=load_skill("model-inspector"),
        markdown=True,
        debug_mode=True,
        tool_call_limit=20,
    )
