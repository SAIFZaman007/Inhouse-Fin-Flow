"""
app/core/cloudinary_service.py
════════════════════════════════════════════════════════════════════════════════
Cloudinary integration for card screenshot uploads.

FIX (v2): cloudinary.uploader.upload / .destroy are SYNCHRONOUS blocking calls.
Running them directly in an async FastAPI handler stalls the event loop and
causes the "Internal Server Error / database error" symptom.
Both helpers now run the blocking SDK calls via asyncio.get_event_loop()
.run_in_executor(None, ...) so the event loop is never blocked.

Environment variables required:
  CLOUDINARY_CLOUD_NAME
  CLOUDINARY_API_KEY
  CLOUDINARY_API_SECRET

All card screenshots are stored as private resources under:
  card_sharing/{serial_no}/{timestamp}

Private delivery type means URLs are only accessible via signed URLs —
no one can access the images without a valid Cloudinary signature.
════════════════════════════════════════════════════════════════════════════════
"""
import asyncio
from functools import partial

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile

from app.core.config import settings

# Configure once at import time
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


async def upload_card_screenshot(file: UploadFile, card_serial: str) -> dict:
    """
    Upload a card screenshot to Cloudinary (async-safe).

    The SDK's upload() is blocking; we offload it to a thread via
    run_in_executor so the FastAPI event loop is never stalled.

    Args:
        file:        FastAPI UploadFile object.
        card_serial: The card's serialNo — used as subfolder name.

    Returns:
        dict with keys: secure_url, public_id, width, height, format, bytes

    Raises:
        HTTPException 400 — invalid file type or size
        HTTPException 502 — Cloudinary upload failure
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid file type '{file.content_type}'. "
                "Allowed: JPEG, PNG, WebP, GIF"
            ),
        )

    contents = await file.read()

    if len(contents) > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(contents) // 1024} KB). Maximum: 10 MB",
        )

    loop = asyncio.get_event_loop()

    # ── Offload the blocking SDK call to a thread pool ────────────────────────
    upload_fn = partial(
        cloudinary.uploader.upload,
        contents,
        folder=f"card_sharing/{card_serial}",
        resource_type="image",
        type="private",          # signed URLs only — suits financial data
        tags=["card_sharing", card_serial],
        unique_filename=True,
        overwrite=False,
    )
    try:
        result = await loop.run_in_executor(None, upload_fn)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Cloudinary upload failed: {exc}",
        )

    return {
        "secure_url": result["secure_url"],
        "public_id":  result["public_id"],
        "width":      result.get("width"),
        "height":     result.get("height"),
        "format":     result.get("format"),
        "bytes":      result.get("bytes"),
    }


async def delete_card_screenshot(public_id: str) -> bool:
    """
    Delete a Cloudinary asset by public_id (async-safe).
    Returns True if deleted, False otherwise.
    """
    loop = asyncio.get_event_loop()
    destroy_fn = partial(
        cloudinary.uploader.destroy,
        public_id,
        resource_type="image",
        type="private",
    )
    try:
        result = await loop.run_in_executor(None, destroy_fn)
        return result.get("result") == "ok"
    except Exception:
        return False