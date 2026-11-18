"""Создаёт icon.ico (атом «МХ») через Pillow. Запуск: python make_icon.py"""
import sys
from PIL import Image, ImageDraw, ImageFont
import logo

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def render(size=256, ss=4):
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # тёмная подложка со скруглением, чтобы значок читался на любом фоне
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=S // 6, fill=(18, 28, 48, 255))
    k = S / 176.0
    cx = cy = S / 2
    g = logo.geometry()
    col = (110, 168, 255, 255)
    for pts in g["orbits"]:
        d.line([(cx + x * k, cy + y * k) for x, y in pts], fill=col, width=max(2, round(g["stroke"] * k * 1.3)), joint="curve")
    for x, y in g["dots"]:
        r = g["dot_r"] * k
        d.ellipse([cx + x * k - r, cy + y * k - r, cx + x * k + r, cy + y * k + r], fill=col)
    r = g["core_r"] * k
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    font = None
    for p in FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(p, int(25 * k)); break
        except OSError:
            continue
    if font:
        d.text((cx, cy), g["text"], fill="white", font=font, anchor="mm")
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    im = render()
    im.save("icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    im.save("icon.png")
    print("icon.ico готов")
