from pydantic import BaseModel, Field

class TransactionTestRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class TokenUsage(BaseModel):
    input: int | None = None
    output: int | None = None
    total: int | None = None


class ExtractionTestResponse(BaseModel):
    data: dict
    model: str
    usage: TokenUsage
