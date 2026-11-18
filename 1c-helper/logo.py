"""Авторский логотип: атом с монограммой «МХ» (геометрия в системе координат SVG viewBox -80 -68 160 136)."""
import math

COLOR = "#6ea8ff"


def ellipse_points(rx=72.0, ry=25.0, angle_deg=0.0, n=90):
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    pts = []
    for i in range(n + 1):
        t = 2 * math.pi * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((x * ca - y * sa, x * sa + y * ca))
    return pts


def geometry():
    """Три орбиты, три электрона (r=6), ядро (r=31) и подпись."""
    orbits = [ellipse_points(angle_deg=a) for a in (0, 60, 120)]
    dots = []
    for a in (0, 60, 120):
        r = math.radians(a)
        dots.append((72 * math.cos(r), 72 * math.sin(r)))
    return {"orbits": orbits, "dots": dots, "dot_r": 6, "core_r": 31, "stroke": 2.6, "text": "МХ"}


def draw_on_canvas(canvas, cx, cy, scale=1.0, color=COLOR, text_color="#ffffff"):
    """Нарисовать логотип на tkinter.Canvas; scale=1 — ширина 160 px."""
    g = geometry()
    for pts in g["orbits"]:
        flat = []
        for x, y in pts:
            flat += [cx + x * scale, cy + y * scale]
        canvas.create_line(*flat, fill=color, width=max(1, round(g["stroke"] * scale)), smooth=False)
    for x, y in g["dots"]:
        r = g["dot_r"] * scale
        canvas.create_oval(cx + x * scale - r, cy + y * scale - r, cx + x * scale + r, cy + y * scale + r, fill=color, outline=color)
    r = g["core_r"] * scale
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline=color)
    canvas.create_text(cx, cy + 9 * scale - 9 * scale, text=g["text"], fill=text_color,
                       font=("Segoe UI", max(6, int(round(19 * scale))), "bold"))
