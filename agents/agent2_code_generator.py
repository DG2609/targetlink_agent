"""
Agent 2: Code Generator (Copilot 1)
Skill: skills/code-generator/SKILL.md
"""

from agno.agent import Agent

from tools.xml_tools import XmlToolkit
from tools.code_tools import CodeToolkit
from utils.skill_loader import load_skill
from utils.model_factory import create_model


def create_agent2(xml_toolkit: XmlToolkit, output_dir: str) -> Agent:
    """Tạo Agent 2 với shared XmlToolkit (chia sẻ cache với Agent 5).

    Args:
        xml_toolkit: Instance XmlToolkit đã khởi tạo (shared cache).
        output_dir: Thư mục output cho generated code.
    """
    return Agent(
        name="Code Generator",
        role="Senior Python Developer viết rule checking scripts",
        model=create_model(),
        tools=[
            xml_toolkit,
            CodeToolkit(output_dir=output_dir),
        ],
        instructions=load_skill("code-generator", include_references=True),
        markdown=True,
        # 20 calls: ~7 explore (hierarchy, block_types, config_locations, blocks, config, xpath, discover)
        #           + ~3 verify + 1 write + buffer cho compound rules
        tool_call_limit=20,
    )
