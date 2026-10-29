"""Optional per-camera product images, stored separately from card JavaScript."""

from __future__ import annotations

from contextlib import suppress
from hashlib import sha256
from pathlib import Path
import os
import tempfile

from homeassistant.components.file_upload import process_uploaded_file
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_SIZE = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000
MAX_DIMENSION = 1600
_ALLOWED_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})


class InvalidProductImage(ValueError):
    """Uploaded file is not an allowed, safe image."""


def _filename(serial: str) -> str:
    """Stable opaque filename: no serial number is exposed in the URL."""
    return f"camera-{sha256(serial.strip().upper().encode('utf-8')).hexdigest()[:24]}.png"


def image_path(hass, serial: str) -> Path:
    """Only use a generated filename; never a user-provided path."""
    return Path(hass.config.path("www", "luxe-ezviz", "images", _filename(serial)))


def image_url(hass, serial: str) -> str | None:
    """Cache-busted public URL for the current upload, if any."""
    path = image_path(hass, serial)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return f"/local/luxe-ezviz/images/{path.name}?v={stat.st_mtime_ns}"


def _convert_to_png(source: Path, target: Path) -> None:
    if not source.is_file() or source.stat().st_size > MAX_UPLOAD_SIZE:
        raise InvalidProductImage("image_too_large")
    try:
        with Image.open(source) as opened:
            if opened.format not in _ALLOWED_FORMATS:
                raise InvalidProductImage("invalid_image")
            if opened.width * opened.height > MAX_IMAGE_PIXELS:
                raise InvalidProductImage("image_too_large")
            # Always decode and re-encode: never serve uploaded HTML/SVG or EXIF.
            opened.seek(0)
            opened.load()
            image = ImageOps.exif_transpose(opened)
            image = image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")
            image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
            image.save(target, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as err:
        if isinstance(err, InvalidProductImage):
            raise
        raise InvalidProductImage("invalid_image") from err


def _save_upload(hass, uploaded_file_id: str, serial: str) -> None:
    destination = image_path(hass, serial)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with process_uploaded_file(hass, uploaded_file_id) as uploaded_path:
            with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".png", delete=False) as temporary:
                temporary_name = temporary.name
            _convert_to_png(Path(uploaded_path), Path(temporary_name))
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name)


async def async_save_image(hass, uploaded_file_id: str, serial: str) -> None:
    await hass.async_add_executor_job(_save_upload, hass, uploaded_file_id, serial)


def _delete_image(hass, serial: str) -> None:
    with suppress(FileNotFoundError):
        image_path(hass, serial).unlink()


async def async_delete_image(hass, serial: str) -> None:
    await hass.async_add_executor_job(_delete_image, hass, serial)


async def async_image_url(hass, serial: str) -> str | None:
    return await hass.async_add_executor_job(image_url, hass, serial)
