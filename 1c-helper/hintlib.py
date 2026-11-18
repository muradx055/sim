"""Ядро помощника: словарь подсказок и сопоставление названий элементов (не зависит от Windows)."""
import json
import os
import re

# латинские «двойники» кириллицы (в 1С бывает «1C:Предприятие» с латинской C)
_LOOKALIKE = str.maketrans({"c": "с", "a": "а", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у", "k": "к", "m": "м", "h": "н", "t": "т", "b": "в"})


def norm(s):
    """Нормализация: регистр, ё→е, без & и «…», лишних пробелов."""
    s = str(s or "").lower().replace("ё", "е").translate(_LOOKALIKE)
    s = s.replace("&", "").replace("…", " ").replace("...", " ")
    s = re.sub(r"\s+", " ", s).strip(" :.\t\r\n")
    return s


def detect_ctx(title):
    """По заголовку окна определить режим: launcher / cfg / ent / ''."""
    t = norm(title)
    if "конфигуратор" in t:
        return "cfg"
    if "запуск 1с" in t:
        return "launcher"
    if "1с:предприятие" in t or "1с: предприятие" in t:
        return "ent"
    return ""


def is_1c_process(name, patterns):
    n = (name or "").lower()
    return any(n.startswith(p.lower()) for p in patterns)


def in_region(pt, rect):
    x, y = pt
    l, t, r, b = rect
    return l <= x <= r and t <= y <= b


class HintBook:
    def __init__(self, hints):
        self.hints = []
        for h in hints:
            phrases = [norm(m) for m in h.get("match", []) if norm(m)]
            if not phrases or not h.get("text"):
                continue
            self.hints.append({
                "phrases": phrases,
                "ctx": h.get("ctx"),
                "title": h.get("title") or h["match"][0],
                "text": h["text"],
            })

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data["hints"] if isinstance(data, dict) else data)

    @staticmethod
    def _score(cand, phrase):
        if cand == phrase:
            return 100
        if len(phrase) >= 5 and re.search(r"(?<![а-яa-z0-9])" + re.escape(phrase) + r"(?![а-яa-z0-9])", cand):
            return 50 + min(len(phrase), 30) // 2
        return 0

    def find(self, candidates, ctx=""):
        """candidates — названия элемента по приоритету (сам элемент, затем родители).
        Возвращает (подсказка, совпавшее_название) или (None, None)."""
        best, best_score, best_c = None, 0, None
        for idx, raw in enumerate(candidates):
            c = norm(raw)
            if not c or len(c) > 90:
                continue
            for h in self.hints:
                for ph in h["phrases"]:
                    s = self._score(c, ph)
                    if not s:
                        continue
                    if h["ctx"]:
                        s += 20 if (ctx and ctx in h["ctx"]) else (-30 if ctx else 0)
                    s -= 4 * idx
                    if s > best_score:
                        best, best_score, best_c = h, s, raw
        if best and best_score >= 45:
            return {"title": best["title"], "text": best["text"]}, best_c
        return None, None


def ocr_windows(words, cursor_idx, max_len=4):
    """Из слов строки (в порядке чтения) собрать фразы из 1..max_len подряд идущих слов,
    содержащие слово под курсором. Сначала более длинные."""
    out = []
    n = len(words)
    for ln in range(min(max_len, n), 0, -1):
        for start in range(max(0, cursor_idx - ln + 1), min(cursor_idx, n - ln) + 1):
            out.append(" ".join(words[start:start + ln]))
    return out


class UnknownLog:
    """Дописывает в файл названия элементов, для которых нет подсказки (чтобы пополнять словарь)."""

    def __init__(self, path):
        self.path = path
        self.seen = set()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        self.seen.add(line.rstrip("\n"))
            except OSError:
                pass

    def add(self, ctx, name, ctype=""):
        name = (name or "").strip()
        if not name or len(name) > 90:
            return False
        line = "%s | %s | %s" % (ctx or "-", name, ctype)
        if line in self.seen:
            return False
        self.seen.add(line)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            return False
        return True
