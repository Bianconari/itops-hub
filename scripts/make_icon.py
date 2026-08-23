"""Regenerate resources/icons/app.ico (reproducible build asset).

Usage:  pip install pillow && python scripts/make_icon.py
The icon matches the visual identity of resources/icons/app.svg
(shield + connected nodes) so exe, installer, and docs stay consistent.
"""

from pathlib import Path

from PIL import Image, ImageDraw

TARGET = Path(__file__).resolve().parents[1] / "resources" / "icons" / "app.ico"


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    pts = [(0.50, 0.06), (0.86, 0.19), (0.86, 0.48), (0.50, 0.94), (0.14, 0.48), (0.14, 0.19)]
    shield = [(x * s, y * s) for x, y in pts]
    d.polygon(shield, fill=(37, 99, 235, 255), outline=(30, 58, 138, 255))
    w = max(1, s // 32)
    d.line([*shield, shield[0]], fill=(30, 58, 138, 255), width=w, joint="curve")
    white = (255, 255, 255, 255)

    def node(x: float, y: float, r: float) -> None:
        cx, cy = x * s, y * s
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=white)

    lw = max(1, s // 24)
    d.line([(0.50 * s, 0.34 * s), (0.33 * s, 0.61 * s)], fill=white, width=lw)
    d.line([(0.50 * s, 0.34 * s), (0.67 * s, 0.61 * s)], fill=white, width=lw)
    d.line([(0.33 * s, 0.61 * s), (0.67 * s, 0.61 * s)], fill=white, width=lw)
    node(0.50, 0.34, s * 0.085)
    node(0.33, 0.61, s * 0.065)
    node(0.67, 0.61, s * 0.065)
    return img


if __name__ == "__main__":
    draw(256).save(
        TARGET,
        format="ICO",
        sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)],
        append_images=[draw(64), draw(48), draw(32), draw(16)],
    )
    print(f"written: {TARGET}")
