from typing import Protocol, Any

class LLMPort(Protocol):
    async def parse_transaction(self, text: str) -> dict:
        ...
