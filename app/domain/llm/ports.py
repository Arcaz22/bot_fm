from typing import Optional, Protocol, Any

class LLMPort(Protocol):
    async def parse_transaction(self, text: str) -> dict:
        ...

    async def parse_receipt_image(self, image_bytes: bytes, context: Optional[str] = None) -> dict:
        ...
