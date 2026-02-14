import logging
from typing import Optional
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException

from app.application.usecases.receipt import ProcessReceiptImage
from app.application.dtos.extraction import ReceiptContext
from app.presentation.schemas.receipt import ExtractReceiptResponse, SaveReceiptResponse
from app.core.di import get_process_receipt_usecase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/receipt", tags=["receipt"])


@router.post("/extract", response_model=ExtractReceiptResponse)
async def extract_receipt(
    file: UploadFile = File(..., description="Foto nota/receipt"),
    wallet_name: str = Form(default="BCA", description="Nama wallet untuk pembayaran"),
    default_category: Optional[str] = Form(default=None, description="Category default jika tidak terdeteksi"),
    notes: Optional[str] = Form(default=None, description="Konteks tambahan (misal: belanja bulanan)"),
    usecase: ProcessReceiptImage = Depends(get_process_receipt_usecase)
):
    """
    Extract data dari foto nota TANPA menyimpan ke database.
    Gunakan endpoint ini untuk testing akurasi OCR.
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File harus berupa gambar (jpg, png, etc)")

    # Read image bytes
    image_bytes = await file.read()

    # Build context
    context = ReceiptContext(
        wallet_name=wallet_name,
        default_category=default_category,
        notes=notes
    )

    # Execute usecase
    result = await usecase.extract_only(image_bytes, context)

    return ExtractReceiptResponse(
        success=result.get("success", False),
        data=result.get("data"),
        error=result.get("error"),
        context_applied=result.get("context_applied")
    )


@router.post("/save", response_model=SaveReceiptResponse)
async def save_receipt(
    user_id: int = Form(..., description="Telegram User ID"),
    file: UploadFile = File(..., description="Foto nota/receipt"),
    wallet_name: str = Form(default="BCA", description="Nama wallet untuk pembayaran"),
    default_category: Optional[str] = Form(default=None, description="Category default"),
    notes: Optional[str] = Form(default=None, description="Konteks tambahan"),
    usecase: ProcessReceiptImage = Depends(get_process_receipt_usecase)
):
    """
    Extract data dari foto nota DAN simpan semua item ke database.
    Gunakan endpoint ini untuk full flow testing.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File harus berupa gambar")

    image_bytes = await file.read()

    context = ReceiptContext(
        wallet_name=wallet_name,
        default_category=default_category,
        notes=notes
    )

    # Execute usecase
    result = await usecase.extract_and_save(user_id, image_bytes, context)

    return SaveReceiptResponse(
        success=result["success"],
        message=result["message"]
    )
