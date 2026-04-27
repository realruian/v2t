"""Generate icon.icns from scratch (no design assets needed)."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import subprocess
import shutil

HERE = Path(__file__).parent.resolve()
ICONSET = HERE / "icon.iconset"
ICONS = HERE / "icon.icns"


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Squircle background with macOS Big Sur radius (~22.5% of size)
    radius = int(size * 0.225)
    # Gradient (simple two-stop) approximated with radial overlay
    bg_top = (10, 132, 255, 255)      # macOS blue
    bg_bot = (60, 100, 220, 255)
    for y in range(size):
        t = y / size
        r = int(bg_top[0] + (bg_bot[0] - bg_top[0]) * t)
        g = int(bg_top[1] + (bg_bot[1] - bg_top[1]) * t)
        b = int(bg_top[2] + (bg_bot[2] - bg_top[2]) * t)
        d.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # Mask to rounded square
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius, fill=255)
    rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rounded.paste(img, (0, 0), mask)

    # Foreground: speech-wave glyph + "T"
    fd = ImageDraw.Draw(rounded)
    cx = size // 2
    cy = size // 2

    # Three vertical bars suggesting audio waveform on the left
    bar_w = max(2, int(size * 0.045))
    gap = int(size * 0.03)
    heights = [0.18, 0.32, 0.22]
    base_x = int(size * 0.22)
    for i, h in enumerate(heights):
        bh = int(size * h)
        x = base_x + i * (bar_w + gap)
        y0 = cy - bh // 2
        y1 = cy + bh // 2
        fd.rounded_rectangle((x, y0, x + bar_w, y1), bar_w // 2, fill=(255, 255, 255, 235))

    # Letter T on the right
    try:
        font_path = "/System/Library/Fonts/SFCompact.ttf"
        if not Path(font_path).exists():
            font_path = "/System/Library/Fonts/Helvetica.ttc"
        font = ImageFont.truetype(font_path, int(size * 0.50))
    except Exception:
        font = ImageFont.load_default()
    text = "T"
    bbox = fd.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = int(size * 0.55) - bbox[0]
    ty = cy - th // 2 - bbox[1]
    fd.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    return rounded


def main():
    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir()

    # Apple's required iconset sizes
    pairs = [
        (16, "16x16"), (32, "16x16@2x"),
        (32, "32x32"), (64, "32x32@2x"),
        (128, "128x128"), (256, "128x128@2x"),
        (256, "256x256"), (512, "256x256@2x"),
        (512, "512x512"), (1024, "512x512@2x"),
    ]
    for px, name in pairs:
        img = draw(px)
        img.save(ICONSET / f"icon_{name}.png")
        print(f"  ✓ {name} ({px}px)")

    if ICONS.exists():
        ICONS.unlink()
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICONS)], check=True)
    shutil.rmtree(ICONSET)
    print(f"✅ {ICONS}")


if __name__ == "__main__":
    main()
