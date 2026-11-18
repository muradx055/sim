import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import hintlib  # noqa: E402

HINTS = os.path.join(os.path.dirname(__file__), "..", "hints_1c.json")


def book():
    return hintlib.HintBook.load(HINTS)


def test_dictionary_is_valid():
    data = json.load(open(HINTS, encoding="utf-8"))
    assert len(data["hints"]) >= 100
    seen = set()
    for h in data["hints"]:
        assert h["match"] and h["text"] and h["title"]
        assert set(h.get("ctx", [])) <= {"launcher", "cfg", "ent"}
        for m in h["match"]:
            key = (hintlib.norm(m), tuple(h.get("ctx", [])))
            assert key not in seen, "дубликат подсказки: %r" % (key,)
            seen.add(key)


def test_exact_and_case_insensitive():
    h, _ = book().find(["записать и закрыть"], "ent")
    assert h and h["title"] == "Записать и закрыть"
    h, _ = book().find(["&Провести и закрыть"], "ent")
    assert h and h["title"] == "Провести и закрыть"


def test_context_decides():
    b = book()
    h, _ = b.find(["Добавить"], "launcher")
    assert "информационной базы" in h["text"]
    h, _ = b.find(["Справочники"], "cfg")
    assert "ПКМ" in h["text"]
    h, _ = b.find(["Справочники"], "ent")
    assert "Раздел" in h["text"]


def test_yo_and_lookalike_letters():
    b = book()
    assert b.find(["Отчёты"], "cfg")[0]
    assert b.find(["1C:Предприятие"], "launcher")[0]  # латинская C


def test_short_words_need_exact_match():
    b = book()
    assert b.find(["Кодировка файла"], "ent")[0] is None  # «Код» не должен срабатывать внутри слова
    assert b.find(["ОК"], "")[0]


def test_menu_item_with_hotkey():
    h, _ = book().find(["Начать отладку F5"], "cfg")
    assert h and "F5" in h["text"]


def test_parent_priority():
    h, c = book().find(["", "Записать", "Провести и закрыть"], "ent")
    assert h["title"] == "Записать"


def test_unknown_returns_none():
    assert book().find(["Совершенно неизвестная кнопка"], "ent") == (None, None)


def test_ocr_windows_pick_best_phrase():
    words = ["Записать", "и", "закрыть", "Провести"]
    h, _ = book().find(hintlib.ocr_windows(words, 1), "ent")
    assert h["title"] == "Записать и закрыть"
    h, _ = book().find(hintlib.ocr_windows(words, 3), "ent")
    assert h["title"] == "Провести"


def test_detect_ctx_and_region_and_process():
    assert hintlib.detect_ctx("Дневник - Конфигуратор") == "cfg"
    assert hintlib.detect_ctx("Запуск 1С:Предприятия") == "launcher"
    assert hintlib.detect_ctx("Дневник / 1С:Предприятие") == "ent"
    assert hintlib.in_region((5, 5), (0, 0, 10, 10)) and not hintlib.in_region((50, 5), (0, 0, 10, 10))
    assert hintlib.is_1c_process("1cv8c.exe", ["1cv8"]) and not hintlib.is_1c_process("chrome.exe", ["1cv8"])


def test_unknown_log_dedup(tmp_path):
    p = str(tmp_path / "u.log")
    u = hintlib.UnknownLog(p)
    assert u.add("cfg", "Что-то", "Button") and not u.add("cfg", "Что-то", "Button")
    assert hintlib.UnknownLog(p).seen
