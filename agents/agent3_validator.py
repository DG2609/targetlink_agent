"""
Agent 3: Validator (Reviewer)
Skill: skills/validator/SKILL.md
"""

from agno.agent import Agent
from agno.models.google import Gemini

from config import settings
from tools.sandbox_tools import SandboxToolkit
from schemas.validation_schemas import ValidationResult
from utils.skill_loader import load_skill


def create_agent3(model_dir: str) -> Agent:
    return Agent(
        name="Validator",
        role="QA Tester chạy code sandbox và đối chiếu kết quả",
        model=Gemini(
            id=settings.GEMINI_MODEL,
            vertexai=True,
            project_id=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        ),
        tools=[
            SandboxToolkit(
                model_dir=model_dir,
                timeout=settings.SANDBOX_TIMEOUT,
            )
        ],
        instructions=load_skill("validator"),
        output_schema=ValidationResult,
        structured_outputs=True,
    )
