"""
Model factory — trả về LLM model instance dựa trên LLM_PROVIDER config.

Hỗ trợ:
  - "gemini": Google Vertex AI (cloud)
  - "ollama": Local Ollama server

Usage:
    from utils.model_factory import create_model
    model = create_model()           # model chính (Agent 2, 4, 5)
    model = create_model(small=True) # model nhỏ (Agent 0, 1, 1.5)
"""

from config import settings


def create_model(small: bool = False):
    """Tạo LLM model instance dựa trên LLM_PROVIDER.

    Args:
        small: True = dùng model nhỏ cho agents đơn giản (Agent 0, 1, 1.5).
               Chỉ có tác dụng khi provider=ollama và OLLAMA_SMALL_MODEL được set.
               Với Gemini luôn dùng cùng model.

    Returns:
        Agno Model instance (Gemini hoặc Ollama).
    """
    if settings.LLM_PROVIDER == "ollama":
        from agno.models.ollama import Ollama

        model_id = settings.OLLAMA_MODEL
        if small and settings.OLLAMA_SMALL_MODEL:
            model_id = settings.OLLAMA_SMALL_MODEL

        return Ollama(
            id=model_id,
            host=settings.OLLAMA_HOST,
        )

    # Default: Gemini
    from agno.models.google import Gemini

    return Gemini(
        id=settings.GEMINI_MODEL,
        vertexai=True,
        project_id=settings.GOOGLE_CLOUD_PROJECT,
        location=settings.GOOGLE_CLOUD_LOCATION,
    )
