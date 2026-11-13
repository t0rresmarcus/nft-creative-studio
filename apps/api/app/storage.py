import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.config import settings

Image.MAX_IMAGE_PIXELS = 40_000_000


def _path_for(key: str) -> Path:
    path = settings.storage_path / key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_bytes(data: bytes, suffix: str) -> tuple[str, str]:
    digest = hashlib.sha256(data).hexdigest()
    key = f"{digest[:2]}/{digest}{suffix}"
    path = _path_for(key)
    if not path.exists():
        path.write_bytes(data)
    return key, digest


def read_bytes(key: str) -> bytes:
    path = settings.storage_path / key
    if not path.exists():
        raise FileNotFoundError(key)
    return path.read_bytes()


def delete_key(key: str | None) -> None:
    if not key:
        return
    path = settings.storage_path / key
    if path.exists():
        path.unlink()


def open_image(data: bytes) -> Image.Image:
    probe = Image.open(BytesIO(data))
    probe.verify()
    image = Image.open(BytesIO(data))
    image.load()
    if getattr(image, "n_frames", 1) > 1:
        image.seek(0)
    return image


def make_thumbnail(image: Image.Image, size: int = 320) -> bytes:
    thumb = image.convert("RGBA")
    thumb.thumbnail((size, size), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    thumb.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def image_to_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.convert("RGBA").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def image_to_format(image: Image.Image, fmt: str, background: str = "#111111") -> tuple[bytes, str]:
    fmt = fmt.lower()
    if fmt in {"jpg", "jpeg"}:
        rgb = _flatten(image, background).convert("RGB")
        buffer = BytesIO()
        rgb.save(buffer, format="JPEG", quality=92, optimize=True)
        return buffer.getvalue(), ".jpg"
    if fmt == "webp":
        buffer = BytesIO()
        image.convert("RGBA").save(buffer, format="WEBP", quality=90)
        return buffer.getvalue(), ".webp"
    return image_to_png(image), ".png"


def _flatten(image: Image.Image, background: str) -> Image.Image:
    rgba = image.convert("RGBA")
    color = background.lstrip("#")
    if len(color) != 6:
        color = "111111"
    rgb = tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))
    canvas = Image.new("RGBA", rgba.size, rgb + (255,))
    return Image.alpha_composite(canvas, rgba)
