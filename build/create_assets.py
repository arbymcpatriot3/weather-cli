#!/usr/bin/env python3
"""
Generate Clean Shot build assets:
  - cleanshot.ico       (app icon, 6 sizes: 16/32/48/64/128/256)
  - wizard_banner.bmp   (Inno Setup classic left sidebar: 164x314)
  - wizard_icon.bmp     (Inno Setup top-right icon: 55x58)

Usage: python create_assets.py <assets_dir>
"""

import sys
from pathlib import Path

ORANGE = (249, 115, 22)
DARK   = (31,  41,  55)
ZINC   = (161, 161, 170)


def draw_truck(draw, size: int):
    """Orange truck silhouette sized to fit within a (size x size) canvas."""
    s = size
    r = max(2, int(s * 0.04))

    # Cargo trailer body
    draw.rounded_rectangle(
        [int(s*0.08), int(s*0.38), int(s*0.92), int(s*0.65)],
        radius=r, fill=ORANGE,
    )

    # Cab
    draw.rounded_rectangle(
        [int(s*0.56), int(s*0.26), int(s*0.92), int(s*0.40)],
        radius=r, fill=ORANGE,
    )

    # Windshield cutout -- skip at sizes where padding would invert bounds
    cx1, cy1 = int(s*0.56) + max(2, s//20), int(s*0.26) + max(2, s//20)
    cx2, cy2 = int(s*0.92) - max(2, s//20), int(s*0.40) - max(2, s//20)
    if cx2 > cx1 and cy2 > cy1:
        draw.rectangle([cx1, cy1, cx2, cy2], fill=DARK)

    # Wheels
    wr = max(3, int(s * 0.09))
    for wx in [int(s * 0.23), int(s * 0.72)]:
        draw.ellipse([wx - wr, int(s*0.60), wx + wr, int(s*0.60) + wr*2], fill=DARK)

    # Exhaust stack
    ex = int(s * 0.50)
    sw = max(1, s // 24)
    draw.rectangle([ex - sw, int(s*0.12), ex + sw, int(s*0.28)], fill=ORANGE)


def make_icon(assets_dir: Path):
    from PIL import Image, ImageDraw

    SZ = 256
    img = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([1, 1, SZ - 2, SZ - 2], fill=(*DARK, 255))
    draw_truck(draw, SZ)

    path = assets_dir / "cleanshot.ico"
    img.save(path, format="ICO",
             sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
    print(f"  Created {path}")


def make_wizard_banner(assets_dir: Path):
    """Classic Inno Setup left-sidebar: 164 x 314 pixels."""
    from PIL import Image, ImageDraw

    W, H = 164, 314
    img = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    # Orange left stripe
    draw.rectangle([0, 0, 6, H], fill=ORANGE)

    # Truck centered in upper half
    SZ = 90
    truck = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    draw_truck(ImageDraw.Draw(truck), SZ)
    img.paste(truck, ((W - SZ) // 2 + 4, 28), truck)

    # Text
    bold  = _load_font("arialbd.ttf", 17)
    reg   = _load_font("arial.ttf",   11)
    small = _load_font("arial.ttf",   10)

    draw.text((14, 138), "Clean Shot",        fill=ORANGE, font=bold)
    draw.text((14, 161), "Road Intelligence", fill=ZINC,   font=reg)
    draw.text((14, 176), "for Truck Drivers", fill=ZINC,   font=reg)
    draw.line([(14, 198), (W - 14, 198)],     fill=(60, 70, 85), width=1)
    draw.text((14, 207), "v3.0.6",            fill=(90, 100, 115), font=small)
    draw.text((14, 222), "cleanshothq.com",   fill=(90, 100, 115), font=small)

    path = assets_dir / "wizard_banner.bmp"
    img.save(path, format="BMP")
    print(f"  Created {path}")


def make_wizard_icon(assets_dir: Path):
    """Inno Setup top-right icon: 55 x 58 pixels."""
    from PIL import Image, ImageDraw

    W, H = 55, 58
    img = Image.new("RGB", (W, H), DARK)
    SZ = 46
    truck = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    draw_truck(ImageDraw.Draw(truck), SZ)
    img.paste(truck, ((W - SZ) // 2, (H - SZ) // 2), truck)

    path = assets_dir / "wizard_icon.bmp"
    img.save(path, format="BMP")
    print(f"  Created {path}")


def _load_font(name: str, size: int):
    from PIL import ImageFont
    for path in [f"C:/Windows/Fonts/{name}", f"/usr/share/fonts/truetype/msttcorefonts/{name}"]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def main():
    assets_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("assets")
    assets_dir.mkdir(parents=True, exist_ok=True)

    try:
        import PIL  # noqa: F401
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install pillow")
        sys.exit(1)

    print("Generating assets...")
    make_icon(assets_dir)
    make_wizard_banner(assets_dir)
    make_wizard_icon(assets_dir)
    print("Done.")


if __name__ == "__main__":
    main()
