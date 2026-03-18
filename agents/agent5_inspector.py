"""
Agent 5: Model Inspector (Copilot 2)
Skill: skills/model-inspector/SKILL.md
"""

from agno.agent import Agent

from tools.xml_tools import XmlToolkit
from tools.code_tools import CodeToolkit
from utils.skill_loader import load_skill
from utils.model_factory import create_model


def create_agent5(xml_toolkit: XmlToolkit, output_dir: str) -> Agent:
    """Tạo Agent 5 với shared XmlToolkit (chia sẻ cache với Agent 2).

    Args:
        xml_toolkit: Instance XmlToolkit đã khởi tạo (shared cache).
        output_dir: Thư mục output cho rewritten code.
    """
    return Agent(
        name="Model Inspector",
        role="Data Detective điều tra XML tree tìm nguyên nhân kết quả sai",
        model=create_model(),
        tools=[
            xml_toolkit,
            CodeToolkit(output_dir=output_dir),
        ],
        instructions=load_skill("model-inspector"),
        markdown=True,
        debug_mode=True,
        # 20 calls: needs more than Agent 2 — reads code, investigates multiple hypotheses,
        # may escalate (raw_config, deep_search), then rewrites. Budget: ~5 read + ~8 investigate + ~2 verify + 1 write + buffer
        tool_call_limit=20,
    )
