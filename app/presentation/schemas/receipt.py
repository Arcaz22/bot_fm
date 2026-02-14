from pydantic import BaseModel
from typing import Optional


class ExtractReceiptResponse(BaseModel):
    """HTTP Response schema untuk /receipt/extract"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    context_applied: Optional[dict] = None


class SaveReceiptResponse(BaseModel):
    """HTTP Response schema untuk /receipt/save"""
    success: bool
    message: str
