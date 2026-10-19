"""Optional on-device OCR of a runner's split screenshot.

The file is read into memory and not uploaded to an AI service or saved.
Tesseract is an optional system-level dependency; extraction does not verify
athletic performance, and the person must confirm the preview.
"""

import asyncio
import io

import discord

from bot.utils.evidence import validate_proof
from bot.utils.splits import parse_ocr_rows

MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024


class SplitOCRError(ValueError):
    pass


def _read_text(raw: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError

        Image.MAX_IMAGE_PIXELS = 20_000_000
        with Image.open(io.BytesIO(raw)) as original:
            if original.width * original.height > 20_000_000:
                raise SplitOCRError("Screenshot is too large to scan.")
            original.seek(0)
            image = ImageOps.exif_transpose(original).convert("L")
            image.thumbnail((2200, 2800))
            image = ImageEnhance.Contrast(image).enhance(1.6)
            return pytesseract.image_to_string(image, config="--psm 6", timeout=10)
    except ImportError as exc:
        raise SplitOCRError("OCR needs pillow and pytesseract installed.") from exc
    except (OSError, ValueError) as exc:
        if isinstance(exc, SplitOCRError):
            raise
        raise SplitOCRError("Could not open that image. Try a PNG or JPG screenshot.") from exc
    except Exception as exc:
        # Catch missing native Tesseract, timeout, and unsupported image formats.
        raise SplitOCRError(
            "OCR could not read this screenshot. Install the Tesseract engine "
            "on the bot host, or enter splits manually."
        ) from exc


async def extract_splits_from_attachment(
    image: discord.Attachment, sport: str, meters: int,
) -> list[int]:
    try:
        validate_proof(image)
    except ValueError as exc:
        raise SplitOCRError(str(exc)) from exc
    if image.size > MAX_SCREENSHOT_BYTES:
        raise SplitOCRError("Split screenshots must be 8 MB or smaller.")
    try:
        raw = await image.read()
    except discord.HTTPException as exc:
        raise SplitOCRError("Could not read that attachment.") from exc
    if len(raw) > MAX_SCREENSHOT_BYTES:
        raise SplitOCRError("Screenshot exceeds the 8 MB limit.")
    try:
        text = await asyncio.wait_for(asyncio.to_thread(_read_text, raw), timeout=15)
        return parse_ocr_rows(text, sport, meters)
    except asyncio.TimeoutError as exc:
        raise SplitOCRError("Screenshot recognition timed out; try manual entry.") from exc
    except ValueError as exc:
        raise SplitOCRError(str(exc)) from exc
