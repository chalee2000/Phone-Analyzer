"""Draw the SPNI app icon (gold tile, phone, magnifier) → resources/icon.ico + icon.png."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
S = 1024  # draw large, then downsample for smooth edges


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp((248, 215, 122), (176, 120, 18), y / S) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([20, 20, S - 20, S - 20], radius=270, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 20, S - 20, S - 20], radius=270, outline=(255, 255, 255, 90), width=12)
    navy, navy2, gold = (11, 27, 61, 255), (26, 58, 122, 255), (242, 193, 78, 255)
    d.rounded_rectangle([235, 170, 600, 790], radius=80, fill=navy)
    d.rounded_rectangle([278, 235, 557, 683], radius=34, fill=navy2)
    d.line([(310, 555), (375, 470), (440, 525), (525, 395)], fill=gold, width=34, joint="curve")
    d.ellipse([445, 385, 835, 775], fill=navy)
    d.ellipse([480, 420, 800, 740], fill=(52, 98, 196, 255))
    d.ellipse([530, 470, 640, 580], fill=(255, 255, 255, 120))
    d.line([(760, 710), (900, 850)], fill=navy, width=96)
    d.ellipse([852, 802, 948, 898], fill=navy)
    return img


def main() -> None:
    icon = draw()
    out = ROOT / "resources"
    icon.resize((256, 256), Image.LANCZOS).save(out / "icon.png")
    icon.save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", out / "icon.ico")


if __name__ == "__main__":
    main()
