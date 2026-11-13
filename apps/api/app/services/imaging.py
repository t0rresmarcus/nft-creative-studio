"""Pillow image operations shared by the editor, batch runner, and renderer."""

from __future__ import annotations

import random
from collections import deque
from io import BytesIO

import httpx
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from app.config import settings


class ImageError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def ensure_rgba(image: Image.Image) -> Image.Image:
    if image.mode != "RGBA":
        return image.convert("RGBA")
    return image.copy()


def _hex_rgb(value: str) -> tuple[int, int, int]:
    color = (value or "#000000").lstrip("#")
    if len(color) != 6:
        raise ImageError("Colors must be hex values like #112233")
    try:
        return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as exc:
        raise ImageError("Colors must be hex values like #112233") from exc


def flatten(image: Image.Image, background: str) -> Image.Image:
    rgba = ensure_rgba(image)
    canvas = Image.new("RGBA", rgba.size, _hex_rgb(background) + (255,))
    return Image.alpha_composite(canvas, rgba)


def _with_alpha(rgb_image: Image.Image, alpha: Image.Image) -> Image.Image:
    merged = rgb_image.convert("RGBA")
    merged.putalpha(alpha)
    return merged


def enhance(image: Image.Image, kind: str, factor: float) -> Image.Image:
    rgba = ensure_rgba(image)
    alpha = rgba.getchannel("A")
    rgb = rgba.convert("RGB")
    factor = float(factor)
    if kind == "brightness":
        rgb = ImageEnhance.Brightness(rgb).enhance(factor)
    elif kind == "contrast":
        rgb = ImageEnhance.Contrast(rgb).enhance(factor)
    elif kind == "saturation":
        rgb = ImageEnhance.Color(rgb).enhance(factor)
    else:
        raise ImageError(f"Unknown color adjustment {kind}")
    return _with_alpha(rgb, alpha)


def shift_hue(image: Image.Image, degrees: float) -> Image.Image:
    rgba = ensure_rgba(image)
    alpha = rgba.getchannel("A")
    hsv = rgba.convert("RGB").convert("HSV")
    hue, saturation, value = hsv.split()
    shift = int(round((degrees % 360) / 360 * 255))
    hue = hue.point(lambda pixel: (pixel + shift) % 256)
    rgb = Image.merge("HSV", (hue, saturation, value)).convert("RGB")
    return _with_alpha(rgb, alpha)


def crop_image(image: Image.Image, x: int, y: int, width: int, height: int) -> Image.Image:
    rgba = ensure_rgba(image)
    x = int(x)
    y = int(y)
    width = int(width)
    height = int(height)
    if width < 1 or height < 1:
        raise ImageError("Crop width and height must be at least 1")
    right = min(rgba.width, x + width)
    bottom = min(rgba.height, y + height)
    left = min(max(x, 0), rgba.width - 1)
    top = min(max(y, 0), rgba.height - 1)
    if right <= left or bottom <= top:
        raise ImageError("Crop rectangle is outside the image")
    return rgba.crop((left, top, right, bottom))


def resize_image(image: Image.Image, width: int, height: int, fit: str = "exact") -> Image.Image:
    rgba = ensure_rgba(image)
    width = int(width)
    height = int(height)
    if width < 1 or height < 1 or width > 8000 or height > 8000:
        raise ImageError("Resize dimensions must be between 1 and 8000")
    fit = fit or "exact"
    if fit == "exact":
        return rgba.resize((width, height), Image.Resampling.LANCZOS)
    if fit == "contain":
        contained = rgba.copy()
        contained.thumbnail((width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        offset = ((width - contained.width) // 2, (height - contained.height) // 2)
        canvas.paste(contained, offset, contained)
        return canvas
    if fit == "cover":
        scale = max(width / rgba.width, height / rgba.height)
        resized = rgba.resize((max(1, int(rgba.width * scale)), max(1, int(rgba.height * scale))), Image.Resampling.LANCZOS)
        left = max(0, (resized.width - width) // 2)
        top = max(0, (resized.height - height) // 2)
        return resized.crop((left, top, left + width, top + height))
    raise ImageError("Fit must be exact, contain, or cover")


def rotate_image(image: Image.Image, degrees: float) -> Image.Image:
    return ensure_rgba(image).rotate(-float(degrees), expand=True, resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))


def flip_image(image: Image.Image, axis: str) -> Image.Image:
    rgba = ensure_rgba(image)
    if axis == "horizontal":
        return ImageOps.mirror(rgba)
    if axis == "vertical":
        return ImageOps.flip(rgba)
    raise ImageError("Flip axis must be horizontal or vertical")


def remove_corner_background(image: Image.Image, tolerance: int = 32) -> Image.Image:
    rgba = ensure_rgba(image)
    width, height = rgba.size
    if width == 0 or height == 0:
        return rgba
    raw = bytearray(rgba.tobytes())
    corners = (0, width - 1, (height - 1) * width, (height - 1) * width + (width - 1))
    if any(raw[index * 4 + 3] < 16 for index in (0, width - 1)):
        return rgba
    tolerance = max(0, min(int(tolerance), 255))
    target = raw[0:3]

    def close(pixel_index: int) -> bool:
        offset = pixel_index * 4
        if raw[offset + 3] < 16:
            return False
        return (
            abs(raw[offset] - target[0]) <= tolerance
            and abs(raw[offset + 1] - target[1]) <= tolerance
            and abs(raw[offset + 2] - target[2]) <= tolerance
        )

    seen = bytearray(width * height)
    queue: deque[int] = deque()
    for start in corners:
        if close(start):
            seen[start] = 1
            queue.append(start)
    while queue:
        pixel = queue.popleft()
        raw[pixel * 4 + 3] = 0
        x = pixel % width
        y = pixel // width
        for nxt in (pixel - 1 if x else None, pixel + 1 if x + 1 < width else None, pixel - width if y else None, pixel + width if y + 1 < height else None):
            if nxt is None or seen[nxt]:
                continue
            seen[nxt] = 1
            if close(nxt):
                queue.append(nxt)
    return Image.frombytes("RGBA", (width, height), bytes(raw))


def _remote_bytes(path: str, data: bytes) -> bytes | None:
    if not settings.ai_endpoint:
        return None
    try:
        response = httpx.post(
            settings.ai_endpoint.rstrip("/") + path,
            files={"file": ("image.png", data, "image/png")},
            timeout=120,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    content_type = response.headers.get("content-type", "")
    if "image" not in content_type and not response.content.startswith(b"\x89PNG"):
        return None
    return response.content


def remove_background(image: Image.Image, tolerance: int = 32, mode: str = "corner") -> tuple[Image.Image, str]:
    buffer = BytesIO()
    ensure_rgba(image).save(buffer, format="PNG")
    payload = buffer.getvalue()
    if mode == "ai":
        remote = _remote_bytes("/remove-background", payload)
        if remote:
            opened = Image.open(BytesIO(remote))
            opened.load()
            return ensure_rgba(opened), "remote"
        try:
            from rembg import remove as rembg_remove

            cut = rembg_remove(payload)
            opened = Image.open(BytesIO(cut))
            opened.load()
            return ensure_rgba(opened), "rembg"
        except Exception:
            return remove_corner_background(image, tolerance), "corner-fallback"
    return remove_corner_background(image, tolerance), "corner"


def replace_background(image: Image.Image, color: str, tolerance: int = 32, mode: str = "corner") -> tuple[Image.Image, str]:
    cut, method = remove_background(image, tolerance=tolerance, mode=mode)
    canvas = Image.new("RGBA", cut.size, _hex_rgb(color) + (255,))
    return Image.alpha_composite(canvas, cut), method


def inpaint_rect(image: Image.Image, x: int, y: int, width: int, height: int) -> Image.Image:
    rgba = ensure_rgba(image)
    x, y, width, height = int(x), int(y), int(width), int(height)
    if width < 1 or height < 1:
        raise ImageError("Removal rectangle must be at least 1×1")
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(rgba.width, x + width), min(rgba.height, y + height)
    if x1 <= x0 or y1 <= y0:
        raise ImageError("Removal rectangle is outside the image")
    pixels = rgba.load()
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            choices: list[tuple[int, int, int]] = []
            if x0 - 1 >= 0:
                choices.append((xx - (x0 - 1), x0 - 1, yy))
            if x1 < rgba.width:
                choices.append((x1 - xx, x1, yy))
            if y0 - 1 >= 0:
                choices.append((yy - (y0 - 1), xx, y0 - 1))
            if y1 < rgba.height:
                choices.append((y1 - yy, xx, y1))
            if not choices:
                continue
            _, sx, sy = min(choices, key=lambda item: item[0])
            pixels[xx, yy] = pixels[sx, sy]
    return rgba


def sharpen(image: Image.Image) -> Image.Image:
    rgba = ensure_rgba(image)
    alpha = rgba.getchannel("A")
    rgb = rgba.convert("RGB").filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=2))
    return _with_alpha(rgb, alpha)


def composite(size: tuple[int, int], layers: list[dict]) -> Image.Image:
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    for layer in layers:
        source: Image.Image = layer["image"]
        sprite = ensure_rgba(source)
        scale = float(layer.get("scale", 1) or 1)
        if scale != 1:
            sprite = sprite.resize(
                (max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale))),
                Image.Resampling.LANCZOS,
            )
        opacity = float(layer.get("opacity", 1))
        if opacity < 1:
            alpha = sprite.getchannel("A").point(lambda pixel: int(pixel * max(0, opacity)))
            sprite.putalpha(alpha)
        x = int(layer.get("x", 0))
        y = int(layer.get("y", 0))
        sheet = Image.new("RGBA", size, (0, 0, 0, 0))
        sheet.paste(sprite, (x, y), sprite)
        canvas = Image.alpha_composite(canvas, sheet)
    return canvas


def apply_operation(image: Image.Image, operation: dict) -> tuple[Image.Image, str | None]:
    kind = operation.get("type") or operation.get("op")
    params = operation.get("params") or {}
    note = None
    if kind == "crop":
        image = crop_image(image, params.get("x", 0), params.get("y", 0), params.get("width", image.width), params.get("height", image.height))
    elif kind == "resize":
        image = resize_image(image, params.get("width", image.width), params.get("height", image.height), params.get("fit", "exact"))
    elif kind == "rotate":
        image = rotate_image(image, params.get("degrees", 0))
    elif kind == "flip":
        image = flip_image(image, params.get("axis", "horizontal"))
    elif kind in {"brightness", "contrast", "saturation"}:
        image = enhance(image, kind, params.get("factor", 1))
    elif kind == "hue":
        image = shift_hue(image, params.get("degrees", 0))
    elif kind == "sharpen":
        image = sharpen(image)
    elif kind == "remove_background":
        image, note = remove_background(image, int(params.get("tolerance", 32)), params.get("mode", "corner"))
    elif kind == "replace_background":
        image, note = replace_background(image, params.get("color", "#ffffff"), int(params.get("tolerance", 32)), params.get("mode", "corner"))
    elif kind == "inpaint":
        image = inpaint_rect(image, params.get("x", 0), params.get("y", 0), params.get("width", 1), params.get("height", 1))
    elif kind in {"format", "rename"}:
        return image, None
    else:
        raise ImageError(f"Unknown operation {kind}")
    return image, note


def condition_matches(operation: dict, image: Image.Image, filename: str) -> bool:
    condition = operation.get("when")
    if not condition:
        return True
    field = condition.get("field", "width")
    op = condition.get("op", "lt")
    expected = condition.get("value")
    if field == "width":
        actual = image.width
    elif field == "height":
        actual = image.height
    elif field == "format":
        actual = filename.rsplit(".", 1)[-1].lower()
    elif field == "filename":
        actual = filename.lower()
        expected = str(expected).lower()
    else:
        return True
    if op == "lt":
        return actual < expected
    if op == "lte":
        return actual <= expected
    if op == "gt":
        return actual > expected
    if op == "gte":
        return actual >= expected
    if op == "eq":
        return actual == expected
    if op == "contains":
        return str(expected) in str(actual)
    return True


def resolve_params(operation: dict, seed: int) -> dict:
    params = dict(operation.get("params") or {})
    ranges = operation.get("random") or {}
    if not ranges:
        return params
    rng = random.Random(seed)
    for name, bounds in ranges.items():
        if not isinstance(bounds, dict):
            continue
        low = float(bounds.get("min", 0))
        high = float(bounds.get("max", low))
        if high < low:
            low, high = high, low
        params[name] = round(rng.uniform(low, high), 4)
    return params


def run_operations(image: Image.Image, operations: list[dict], seed: int = 1, filename: str = "image.png") -> tuple[Image.Image, list[str]]:
    notes: list[str] = []
    current = ensure_rgba(image)
    for index, operation in enumerate(operations):
        if not condition_matches(operation, current, filename):
            continue
        prepared = dict(operation)
        prepared["params"] = resolve_params(operation, seed + index * 17)
        current, note = apply_operation(current, prepared)
        if note:
            notes.append(note)
    return current, notes


def variations(image: Image.Image, count: int, seed: int) -> list[Image.Image]:
    count = max(1, min(int(count), 12))
    rng = random.Random(seed)
    results = []
    for _ in range(count):
        current = enhance(image, "brightness", 0.9 + rng.random() * 0.25)
        current = enhance(current, "contrast", 0.9 + rng.random() * 0.3)
        current = enhance(current, "saturation", 0.8 + rng.random() * 0.4)
        current = shift_hue(current, rng.randint(-18, 18))
        results.append(current)
    return results


def dhash(image: Image.Image, hash_size: int = 8) -> str:
    gray = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = list(gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata())
    bits = 0
    bit_index = 0
    row_width = hash_size + 1
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[row * row_width + col]
            right = pixels[row * row_width + col + 1]
            if left > right:
                bits |= 1 << bit_index
            bit_index += 1
    return f"{bits:016x}"


def hamming(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def draw_placeholder(width: int, height: int, label: str, color: tuple[int, int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(image)
    drawing.rectangle((0, 0, width - 1, height - 1), fill=color)
    return image
