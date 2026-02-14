import logging
from typing import Optional

from app.application.services.receipt_service import ReceiptService
from app.application.dtos.extraction import ReceiptContext

logger = logging.getLogger(__name__)


class ProcessReceiptImage:
    """
    UseCase: Handle receipt image processing request

    Responsibilities:
    - Validate input
    - Orchestrate service call
    - Format output sesuai kebutuhan caller (HTTP/Telegram)
    """

    def __init__(self, receipt_service: ReceiptService):
        self.service = receipt_service

    async def extract_only(
        self,
        image_bytes: bytes,
        context: Optional[ReceiptContext] = None
    ) -> dict:
        """
        UseCase: Extract receipt data tanpa save (untuk preview/testing)
        Returns dict yang siap diformat jadi HTTP/Telegram response
        """
        logger.info(f"UseCase: Extract receipt (size: {len(image_bytes)} bytes)")

        # Validate input
        if len(image_bytes) == 0:
            return {
                "success": False,
                "error": "Image data kosong"
            }

        if len(image_bytes) > 10 * 1024 * 1024:  # 10MB
            return {
                "success": False,
                "error": "Ukuran gambar terlalu besar (max 10MB)"
            }

        # Call service
        result = await self.service.extract_from_image(image_bytes, context)

        return result

    async def extract_and_save(
        self,
        user_id: int,
        image_bytes: bytes,
        context: Optional[ReceiptContext] = None
    ) -> dict:
        """
        UseCase: Extract receipt dan simpan semua items ke database
        Returns dict dengan status + message
        """
        logger.info(f"UseCase: Extract & Save receipt for user {user_id}")

        # Validate input
        if user_id <= 0:
            return {
                "success": False,
                "message": "❌ User ID tidak valid"
            }

        if len(image_bytes) == 0:
            return {
                "success": False,
                "message": "❌ Image data kosong"
            }

        if len(image_bytes) > 10 * 1024 * 1024:
            return {
                "success": False,
                "message": "❌ Ukuran gambar terlalu besar (max 10MB)"
            }

        # Call service
        try:
            message = await self.service.process_and_save(user_id, image_bytes, context)

            return {
                "success": "✅" in message,
                "message": message
            }
        except Exception as e:
            logger.error(f"Error in ProcessReceiptImage.extract_and_save: {e}")
            return {
                "success": False,
                "message": f"❌ Terjadi kesalahan: {str(e)}"
            }
