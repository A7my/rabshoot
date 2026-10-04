"""Generate app icons from logo.png: the envelope/plane mark without the wordmark.

Usage: python scripts/make_icons.py   (needs Pillow)
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "logo.png"
TAURI_ICONS = ROOT / "app" / "src-tauri" / "icons"
PUBLIC = ROOT / "app" / "public"
ENGINE_ASSETS = ROOT / "engine" / "rabshoot_engine" / "assets"
ASSETS = ROOT / "assets"

BG = (10, 11, 16, 255)  # #0A0B10


def crop_mark(logo: Image.Image) -> Image.Image:
    """The mark sits in the upper ~57% of the logo; the wordmark is below it."""
    w, h = logo.size
    top = logo.crop((0, 0, w, int(h * 0.57)))
    alpha = top.split()[3].point(lambda a: 255 if a > 24 else 0)
    mark = top.crop(alpha.getbbox())
    side = max(mark.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2), mark)
    return square


def app_icon(mark: Image.Image, size: int) -> Image.Image:
    """Mark on a dark rounded square, like the app's own background."""
    scale = 4
    big = size * scale
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22),
                                           fill=255)
    canvas.paste(Image.new("RGBA", (big, big), BG), (0, 0), mask)
    inner = int(big * 0.82)
    m = mark.resize((inner, inner), Image.LANCZOS)
    canvas.paste(m, ((big - inner) // 2, (big - inner) // 2), m)
    return canvas.resize((size, size), Image.LANCZOS)


def main() -> None:
    logo = Image.open(LOGO).convert("RGBA")
    mark = crop_mark(logo)
    for d in (TAURI_ICONS, PUBLIC, ENGINE_ASSETS, ASSETS):
        d.mkdir(parents=True, exist_ok=True)

    mark.resize((1024, 1024), Image.LANCZOS).save(ASSETS / "mark.png")
    mark.resize((512, 512), Image.LANCZOS).save(PUBLIC / "mark.png")
    mark.resize((96, 96), Image.LANCZOS).save(ENGINE_ASSETS / "mark.png", optimize=True)
    logo.save(PUBLIC / "logo.png", optimize=True)

    icons = {"32x32.png": 32, "64x64.png": 64, "128x128.png": 128, "128x128@2x.png": 256,
             "icon.png": 512, "tray.png": 64}
    for name, size in icons.items():
        app_icon(mark, size).save(TAURI_ICONS / name)
    app_icon(mark, 1024).save(ASSETS / "icon-1024.png")
    app_icon(mark, 256).save(TAURI_ICONS / "icon.ico",
                             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                    (128, 128), (256, 256)])
    # Windows Store style logos referenced by Tauri's defaults.
    for name, size in {"Square30x30Logo.png": 30, "Square44x44Logo.png": 44,
                       "Square71x71Logo.png": 71, "Square89x89Logo.png": 89,
                       "Square107x107Logo.png": 107, "Square142x142Logo.png": 142,
                       "Square150x150Logo.png": 150, "Square284x284Logo.png": 284,
                       "Square310x310Logo.png": 310, "StoreLogo.png": 50}.items():
        app_icon(mark, size).save(TAURI_ICONS / name)
    app_icon(mark, 64).save(PUBLIC / "favicon.png")
    print("Icons written to", TAURI_ICONS)


if __name__ == "__main__":
    main()
