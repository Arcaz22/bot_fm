from app.core.settings import settings
from app.domain.llm.ports import LLMPort


def create_llm_client(provider: str | None = None) -> LLMPort:
    selected = (provider or settings.LLM_PROVIDER).strip().lower()

    if selected == "ollama":
        from app.infrastructure.llm.ollama_client import OllamaLLM

        return OllamaLLM()
    if selected == "mock":
        from app.infrastructure.llm.mock_client import MockLLM

        return MockLLM()
    if selected == "gemini":
        from app.infrastructure.llm.client import GeminiLLM

        return GeminiLLM()

    raise ValueError(
        f"LLM_PROVIDER '{selected}' tidak didukung. Gunakan: gemini, ollama, atau mock."
    )
