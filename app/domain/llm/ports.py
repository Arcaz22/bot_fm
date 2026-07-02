from typing import Optional, Protocol

class LLMPort(Protocol):
    async def parse_transaction(self, text: str, include_usage: bool = False) -> dict:
        ...

    async def parse_receipt_image(
        self,
        image_bytes: bytes,
        context: Optional[str] = None,
        include_usage: bool = False,
    ) -> dict:
        ...
