"""
Agent 4: Bug Fixer
Skill: skills/bug-fixer/SKILL.md
"""

from agno.agent import Agent

from config import settings
from tools.code_tools import CodeToolkit
from tools.xml_tools import XmlToolkit
from utils.skill_loader import load_skill
from utils.model_factory import create_model


def create_agent4(
    xml_toolkit: XmlToolkit | None = None,
    output_dir: str | None = None,
) -> Agent:
    """Tạo Agent 4 — Bug Fixer.

    Args:
        xml_toolkit: Shared XmlToolkit (optional). Nếu có, Agent 4 có thể verify XPath.
        output_dir: Thư mục output cho code tools. Default: settings.GENERATED_CHECKS_DIR.
    """
    tools: list = [CodeToolkit(output_dir=output_dir or str(settings.GENERATED_CHECKS_DIR))]
    if xml_toolkit:
        tools.append(xml_toolkit)

    return Agent(
        name="Bug Fixer",
        role="Kỹ sư sửa lỗi code dựa trên error traceback",
        model=create_model(),
        tools=tools,
        instructions=load_skill("bug-fixer"),
        markdown=True,
        # 15 calls: reads code (~2), XML verify (~3-4 nếu có), fixes (~1-2 rewrites), buffer
        tool_call_limit=15,
    )
