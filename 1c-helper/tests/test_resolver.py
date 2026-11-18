import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import hintlib  # noqa: E402
import helper  # noqa: E402

HINTS = os.path.join(os.path.dirname(__file__), "..", "hints_1c.json")


class Ctl:
    def __init__(self, name, parent=None, pid=100, ctype="ButtonControl", help_text=""):
        self.Name, self._p, self.ProcessId, self.ControlTypeName, self.HelpText = name, parent, pid, ctype, help_text

    def GetParentControl(self):
        return self._p

    def GetTopLevelControl(self):
        n = self
        while n._p is not None:
            n = n._p
        return n


def make(monkeypatch, tmp_path, ctrl, **over):
    fake = types.ModuleType("uiautomation")
    fake.ControlFromPoint = lambda x, y: ctrl
    monkeypatch.setitem(sys.modules, "uiautomation", fake)
    s = dict(helper.DEFAULTS, ocr=False, **over)
    r = helper.Resolver(hintlib.HintBook.load(HINTS), s, hintlib.UnknownLog(str(tmp_path / "u.log")))
    r.proc_cache[100] = "1cv8.exe"
    r.proc_cache[200] = "notepad.exe"
    return r


def test_finds_hint_in_1c_window(monkeypatch, tmp_path):
    win = Ctl("Дневник / 1С:Предприятие", ctype="WindowControl")
    r = make(monkeypatch, tmp_path, Ctl("Записать и закрыть", win))
    assert r.lookup(10, 10)["title"] == "Записать и закрыть"


def test_label_inside_button_uses_parent_name(monkeypatch, tmp_path):
    win = Ctl("Дневник - Конфигуратор", ctype="WindowControl")
    btn = Ctl("Справочники", win)
    r = make(monkeypatch, tmp_path, Ctl("", btn, ctype="TextControl"))
    assert "ПКМ" in r.lookup(10, 10)["text"]


def test_other_programs_ignored_in_1c_mode(monkeypatch, tmp_path):
    r = make(monkeypatch, tmp_path, Ctl("Записать и закрыть", Ctl("Блокнот", pid=200), pid=200))
    assert r.lookup(10, 10) is None


def test_all_mode_and_region_mode(monkeypatch, tmp_path):
    ctl = Ctl("Закрыть", Ctl("Что-то", pid=200), pid=200)
    assert make(monkeypatch, tmp_path, ctl, mode="all").lookup(10, 10)
    assert make(monkeypatch, tmp_path, ctl, mode="region", region=[0, 0, 50, 50]).lookup(10, 10)
    assert make(monkeypatch, tmp_path, ctl, mode="region", region=[100, 100, 150, 150]).lookup(10, 10) is None


def test_learn_mode_logs_unknown(monkeypatch, tmp_path):
    win = Ctl("Дневник - Конфигуратор", ctype="WindowControl")
    r = make(monkeypatch, tmp_path, Ctl("Какая-то новая кнопка", win), learn=True)
    out = r.lookup(10, 10)
    assert out["title"] == "Нет подсказки"
    assert "Какая-то новая кнопка" in (tmp_path / "u.log").read_text(encoding="utf-8")
