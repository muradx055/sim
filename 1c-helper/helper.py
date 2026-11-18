# -*- coding: utf-8 -*-
"""Помощник по 1С: показывает пояснения к кнопкам и меню при наведении мыши.
Запуск: helper.exe  (или python helper.py).  Проверка: helper.exe --selftest
"""
import json
import os
import queue
import sys
import threading
import time

import hintlib
import logo

APP_TITLE = "Помощник по 1С"
IS_WIN = sys.platform == "win32"
FROZEN = getattr(sys, "frozen", False)
BASE_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
UNKNOWN_PATH = os.path.join(BASE_DIR, "unknown.log")
DEFAULTS = {"mode": "1c", "region": None, "ocr": True, "learn": False, "delay": 0.45,
            "processes": ["1cv8", "1cestart", "1cv8c", "1cv8s"]}


def find_hints_path():
    for d in (BASE_DIR, BUNDLE_DIR):
        p = os.path.join(d, "hints_1c.json")
        if os.path.exists(p):
            return p
    raise FileNotFoundError("hints_1c.json не найден рядом с программой")


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


# ---------------- Windows API ----------------
if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    def enable_dpi_awareness():
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass

    def cursor_pos():
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def key_down(vk):
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    def make_click_through(tk_window):
        """Окно подсказки не перехватывает мышь и не забирает фокус."""
        try:
            hwnd = user32.GetParent(tk_window.winfo_id()) or tk_window.winfo_id()
            GWL_EXSTYLE = -20
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= 0x80000 | 0x20 | 0x08000000 | 0x80  # LAYERED | TRANSPARENT | NOACTIVATE | TOOLWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def virtual_screen():
        return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
                user32.GetSystemMetrics(76) + user32.GetSystemMetrics(78),
                user32.GetSystemMetrics(77) + user32.GetSystemMetrics(79))
else:
    def enable_dpi_awareness():
        pass

    def cursor_pos():
        return 0, 0

    def key_down(vk):
        return False

    def make_click_through(tk_window):
        pass

    def virtual_screen():
        return 0, 0, 1920, 1080


# ---------------- распознавание элемента под курсором ----------------
class Resolver:
    def __init__(self, book, settings, unknown):
        self.book, self.s, self.unknown = book, settings, unknown
        self.proc_cache = {}
        self.ocr_ok = None
        self.ocr_lang = None
        self.ocr_err = ""
        self.last_debug = ""

    def _proc_name(self, pid):
        if pid in self.proc_cache:
            return self.proc_cache[pid]
        name = ""
        try:
            import psutil
            name = psutil.Process(pid).name()
        except Exception:
            pass
        self.proc_cache[pid] = name
        return name

    def allowed(self, pt, pid=None):
        mode = self.s["mode"]
        if mode == "all":
            return True
        if mode == "region":
            r = self.s.get("region")
            return bool(r) and hintlib.in_region(pt, r)
        return bool(pid) and hintlib.is_1c_process(self._proc_name(pid), self.s["processes"])

    def lookup(self, x, y):
        import uiautomation as auto
        ctrl = auto.ControlFromPoint(x, y)
        pid = ctrl.ProcessId if ctrl else None
        if not self.allowed((x, y), pid):
            return None
        title, cands, ctype = "", [], ""
        if ctrl:
            ctype = ctrl.ControlTypeName
            try:
                top = ctrl.GetTopLevelControl()
                title = top.Name if top else ""
            except Exception:
                title = ""
            node, depth = ctrl, 0
            while node is not None and depth < 4:
                for val in (node.Name, getattr(node, "HelpText", "")):
                    if val and val != title and val not in cands:
                        cands.append(val)
                try:
                    node = node.GetParentControl()
                except Exception:
                    node = None
                depth += 1
        ctx = hintlib.detect_ctx(title)
        hint, _ = self.book.find(cands, ctx)
        if not hint and self.s.get("ocr"):
            hint = self._ocr_hint(x, y, ctx)
        if not hint and self.s.get("learn"):
            for c in cands[:2]:
                self.unknown.add(ctx, c, ctype)
            self.last_debug = "нет подсказки: " + (cands[0] if cands else "<без названия>")
            return {"title": "Нет подсказки", "text": (cands[0] if cands else "элемент без названия") + "\n(записано в unknown.log)"}
        return hint

    # --- OCR (встроенное распознавание Windows 10/11) ---
    def _ocr_hint(self, x, y, ctx):
        try:
            from PIL import ImageGrab
            import winocr
        except Exception as e:  # библиотеки не установлены
            self.ocr_ok, self.ocr_err = False, str(e)
            return None
        W, H = 170, 28
        left, top, right, bottom = x - W, y - H, x + W, y + H
        try:
            img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        except Exception:
            return None
        res = None
        for lang in ([self.ocr_lang] if self.ocr_lang else ["ru", "en-US"]):
            try:
                res = winocr.recognize_pil_sync(img, lang)
                self.ocr_lang, self.ocr_ok = lang, True
                break
            except Exception as e:
                self.ocr_err = str(e)
        if not res:
            self.ocr_ok = self.ocr_ok or False
            return None
        cx, cy = x - left, y - top
        for line in res.get("lines", []):
            words = line.get("words", [])
            for i, w in enumerate(words):
                r = w.get("bounding_rect", {})
                if r.get("x", 1e9) - 8 <= cx <= r.get("x", 0) + r.get("width", 0) + 8 and \
                   r.get("y", 1e9) - 6 <= cy <= r.get("y", 0) + r.get("height", 0) + 6:
                    phrases = hintlib.ocr_windows([ww.get("text", "") for ww in words], i)
                    hint, _ = self.book.find(phrases, ctx)
                    if hint:
                        return hint
        return None


class Watcher(threading.Thread):
    def __init__(self, resolver, settings, out_q):
        super().__init__(daemon=True)
        self.r, self.s, self.q = resolver, settings, out_q
        self.stop_ev = threading.Event()
        self.paused = False

    def run(self):
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread(debug=False):
            last_pos, moved_at, done_for, hotkey_t = (-1, -1), time.time(), None, 0
            while not self.stop_ev.is_set():
                time.sleep(0.05)
                try:
                    if key_down(0x11) and key_down(0x12) and key_down(0x48) and time.time() - hotkey_t > 0.6:  # Ctrl+Alt+H
                        hotkey_t = time.time()
                        self.paused = not self.paused
                        self.q.put(("paused", self.paused))
                        self.q.put(("hide",))
                    if self.paused:
                        continue
                    pos = cursor_pos()
                    if abs(pos[0] - last_pos[0]) > 3 or abs(pos[1] - last_pos[1]) > 3 or key_down(0x01):
                        last_pos, moved_at, done_for = pos, time.time(), None
                        self.q.put(("hide",))
                        continue
                    if done_for == last_pos or time.time() - moved_at < self.s["delay"]:
                        continue
                    done_for = last_pos
                    hint = self.r.lookup(*pos)
                    self.q.put(("show", pos, hint) if hint else ("hide",))
                except Exception as e:  # ошибка одного опроса не должна останавливать помощника
                    self.q.put(("error", repr(e)))
                    done_for = last_pos


def main_gui(selftest=False):
    import tkinter as tk
    from tkinter import ttk, messagebox

    enable_dpi_awareness()
    settings = load_settings()
    book = hintlib.HintBook.load(find_hints_path())
    unknown = hintlib.UnknownLog(UNKNOWN_PATH)
    resolver = Resolver(book, settings, unknown)
    out_q = queue.Queue()

    root = tk.Tk()
    root.title(APP_TITLE)
    root.resizable(False, False)
    try:
        ico = os.path.join(BUNDLE_DIR, "icon.ico")
        if os.path.exists(ico):
            root.iconbitmap(ico)
    except Exception:
        pass

    # ---------- подсказка ----------
    tip = tk.Toplevel(root)
    tip.withdraw()
    tip.overrideredirect(True)
    tip.attributes("-topmost", True)
    tip.attributes("-alpha", 0.97)  # заодно включает «слоистое» окно, на которое опирается make_click_through
    frame = tk.Frame(tip, bg="#fffbe3", highlightbackground="#c9b13c", highlightthickness=1)
    frame.pack()
    head = tk.Frame(frame, bg="#ffe56b")
    head.pack(fill="x")
    lbl_title = tk.Label(head, bg="#ffe56b", fg="#222", font=("Segoe UI", 10, "bold"), anchor="w", justify="left", wraplength=300)
    lbl_title.pack(side="left", padx=8, pady=3)
    mini = tk.Canvas(head, width=30, height=26, bg="#ffe56b", highlightthickness=0)
    mini.pack(side="right", padx=4)
    logo.draw_on_canvas(mini, 15, 13, 0.17, color="#1d3b7a", text_color="#ffe56b")
    lbl_text = tk.Label(frame, bg="#fffbe3", fg="#222", font=("Segoe UI", 10), anchor="w", justify="left", wraplength=340)
    lbl_text.pack(padx=8, pady=6, anchor="w")
    tip.update_idletasks()
    make_click_through(tip)

    def show_tip(pos, hint):
        lbl_title.config(text=hint["title"])
        lbl_text.config(text=hint["text"])
        tip.update_idletasks()
        w, h = tip.winfo_reqwidth(), tip.winfo_reqheight()
        vl, vt, vr, vb = virtual_screen()
        x, y = pos[0] + 18, pos[1] + 24
        if x + w > vr:
            x = max(vl, pos[0] - w - 12)
        if y + h > vb:
            y = max(vt, pos[1] - h - 12)
        tip.geometry("+%d+%d" % (x, y))
        tip.deiconify()
        tip.attributes("-topmost", True)

    # ---------- окно настройки ----------
    hdr = tk.Canvas(root, width=440, height=84, bg="#121c30", highlightthickness=0)
    hdr.pack(fill="x")
    logo.draw_on_canvas(hdr, 70, 42, 0.46)
    hdr.create_text(140, 30, text=APP_TITLE, anchor="w", fill="white", font=("Segoe UI", 17, "bold"))
    hdr.create_text(140, 56, text="подсказки к кнопкам и меню 1С при наведении мыши", anchor="w", fill="#9db8e6", font=("Segoe UI", 9))

    body = ttk.Frame(root, padding=12)
    body.pack(fill="both")
    mode_var = tk.StringVar(value=settings["mode"])
    ttk.Label(body, text="Где показывать подсказки:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Radiobutton(body, text="Только в окнах 1С (по программе 1cv8.exe)", variable=mode_var, value="1c").grid(row=1, column=0, columnspan=2, sticky="w")
    ttk.Radiobutton(body, text="Только в выделенной области экрана", variable=mode_var, value="region").grid(row=2, column=0, sticky="w")
    ttk.Radiobutton(body, text="На всём экране (в любых программах)", variable=mode_var, value="all").grid(row=4, column=0, columnspan=2, sticky="w")
    region_lbl = ttk.Label(body, text="")
    region_lbl.grid(row=3, column=0, sticky="w", padx=24)

    def refresh_region_label():
        r = settings.get("region")
        region_lbl.config(text=("Область: %d×%d (x=%d, y=%d)" % (r[2] - r[0], r[3] - r[1], r[0], r[1])) if r else "Область не выбрана")
    refresh_region_label()

    def pick_region():
        root.withdraw()
        tip.withdraw()
        ov = tk.Toplevel(root)
        vl, vt, vr, vb = virtual_screen()
        ov.overrideredirect(True)
        ov.geometry("%dx%d+%d+%d" % (vr - vl, vb - vt, vl, vt))
        ov.attributes("-alpha", 0.3)
        ov.attributes("-topmost", True)
        ov.configure(bg="black", cursor="crosshair")
        cv = tk.Canvas(ov, bg="black", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        cv.create_text(40, 40, anchor="nw", fill="white", font=("Segoe UI", 16, "bold"),
                       text="Протяните мышью прямоугольник области. Esc — отмена.")
        st = {}

        def down(e):
            st["x0"], st["y0"] = e.x_root, e.y_root
            st["id"] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline="#ffe56b", width=3)

        def move(e):
            if "id" in st:
                cv.coords(st["id"], st["x0"] - vl, st["y0"] - vt, e.x, e.y)

        def up(e):
            if "x0" in st and abs(e.x_root - st["x0"]) > 20 and abs(e.y_root - st["y0"]) > 20:
                settings["region"] = [min(st["x0"], e.x_root), min(st["y0"], e.y_root), max(st["x0"], e.x_root), max(st["y0"], e.y_root)]
                mode_var.set("region")
            close()

        def close(_e=None):
            ov.destroy()
            root.deiconify()
            refresh_region_label()
        cv.bind("<ButtonPress-1>", down)
        cv.bind("<B1-Motion>", move)
        cv.bind("<ButtonRelease-1>", up)
        ov.bind("<Escape>", close)
        ov.focus_force()

    ttk.Button(body, text="Выделить область…", command=pick_region).grid(row=2, column=1, sticky="e")

    ocr_var = tk.BooleanVar(value=settings["ocr"])
    learn_var = tk.BooleanVar(value=settings["learn"])
    ttk.Separator(body).grid(row=5, column=0, columnspan=2, sticky="ew", pady=8)
    ttk.Checkbutton(body, text="Читать надписи с экрана (OCR), если у элемента нет названия", variable=ocr_var).grid(row=6, column=0, columnspan=2, sticky="w")
    ttk.Checkbutton(body, text="Режим словаря: записывать неизвестные элементы в unknown.log", variable=learn_var).grid(row=7, column=0, columnspan=2, sticky="w")
    ttk.Label(body, text="Задержка перед подсказкой, сек:").grid(row=8, column=0, sticky="w", pady=(8, 0))
    delay_var = tk.DoubleVar(value=settings["delay"])
    ttk.Scale(body, from_=0.1, to=1.5, variable=delay_var, length=140).grid(row=8, column=1, sticky="e", pady=(8, 0))

    status = tk.StringVar(value="Остановлено")
    ttk.Label(body, textvariable=status, foreground="#555").grid(row=9, column=0, columnspan=2, sticky="w", pady=(10, 2))
    watcher = {"t": None}

    def apply_settings():
        settings.update({"mode": mode_var.get(), "ocr": ocr_var.get(), "learn": learn_var.get(), "delay": round(delay_var.get(), 2)})
        save_settings(settings)

    def start():
        apply_settings()
        if settings["mode"] == "region" and not settings.get("region"):
            messagebox.showinfo(APP_TITLE, "Сначала выделите область экрана кнопкой «Выделить область…».")
            return
        w = Watcher(resolver, settings, out_q)
        watcher["t"] = w
        w.start()
        btn.config(text="Остановить", command=stop)
        status.set("Работает. Наведите мышь на кнопку 1С. Ctrl+Alt+H — пауза.")

    def stop():
        w = watcher["t"]
        if w:
            w.stop_ev.set()
        watcher["t"] = None
        tip.withdraw()
        btn.config(text="Запустить", command=start)
        status.set("Остановлено")

    btn = ttk.Button(body, text="Запустить", command=start)
    btn.grid(row=10, column=0, sticky="w")
    ttk.Button(body, text="Открыть словарь подсказок", command=lambda: os.startfile(find_hints_path()) if IS_WIN else None).grid(row=10, column=1, sticky="e")

    def poll():
        try:
            while True:
                msg = out_q.get_nowait()
                if msg[0] == "show":
                    show_tip(msg[1], msg[2])
                elif msg[0] == "hide":
                    tip.withdraw()
                elif msg[0] == "paused":
                    status.set("Пауза (Ctrl+Alt+H — продолжить)" if msg[1] else "Работает. Ctrl+Alt+H — пауза.")
                elif msg[0] == "error":
                    status.set("Ошибка опроса: " + msg[1][:70])
        except queue.Empty:
            pass
        root.after(40, poll)

    def on_close():
        stop()
        apply_settings()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(40, poll)

    if selftest:
        root.after(300, lambda: run_selftest(root, tip, show_tip, resolver, book))
    root.mainloop()


def say(msg):
    """Вывод и в консоль (если есть), и в selftest.log: у exe без окна консоли нет."""
    try:
        if sys.stdout:
            print(msg)
    except Exception:
        pass
    try:
        with open(os.path.join(BASE_DIR, "selftest.log"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def run_selftest(root, tip, show_tip, resolver, book):
    """Проверка сборки на Windows: окно, подсказка, UI Automation, словарь, OCR.
    Код возврата 0 — всё важное работает (OCR не обязателен)."""
    ok = True
    try:
        show_tip((200, 200), {"title": "Проверка", "text": "Подсказка отображается."})
        root.update()
        say("[ok] подсказка показана")
        tip.withdraw()
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            c = auto.ControlFromPoint(*cursor_pos())
            say("[ok] UI Automation: элемент под курсором: %s" % (c.ControlTypeName if c else None))
        h, _ = book.find(["Записать и закрыть"], "ent")
        assert h, "словарь не нашёл подсказку"
        say("[ok] словарь: найдено «%s»" % h["title"])
    except Exception as e:
        ok = False
        say("[FAIL] %r" % (e,))
    try:  # OCR не обязателен (на сервере может не быть русского языка распознавания)
        from PIL import Image, ImageDraw, ImageFont
        import winocr
        im = Image.new("RGB", (360, 60), "white")
        ImageDraw.Draw(im).text((10, 10), "Provesti i zakryt", fill="black", font=ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 28))
        for lang in ("ru", "en-US"):
            try:
                r = winocr.recognize_pil_sync(im, lang)
                say("[ok] OCR (%s): %s" % (lang, r.get("text")))
                break
            except Exception as e:
                say("[warn] OCR %s: %s" % (lang, str(e)[:80]))
    except Exception as e:
        say("[warn] OCR недоступен: %s" % str(e)[:100])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if not IS_WIN:
        print("Помощник работает только в Windows.")
        sys.exit(1)
    main_gui(selftest="--selftest" in sys.argv)
