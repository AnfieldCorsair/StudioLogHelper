import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studiologhelper.ui.undo import UndoManager, Command
from studiologhelper.core.settings import AppConfig, UISettings, TextParseSettings, HAS_PYDANTIC


def test_undo_manager():
    state = {"value": 0}
    um = UndoManager()

    def do_inc():
        state["value"] += 1

    def undo_inc():
        state["value"] -= 1

    cmd = Command("inc", do_inc, undo_inc)
    um.execute(cmd)
    assert state["value"] == 1
    assert um.can_undo()

    um.undo()
    assert state["value"] == 0
    assert um.can_redo()

    um.redo()
    assert state["value"] == 1


def test_pydantic_settings_validation():
    if not HAS_PYDANTIC:
        return

    # Valid
    cfg = AppConfig(ui=UISettings(theme="dark", zoom=150))
    assert cfg.ui.zoom == 150

    # Invalid zoom should raise
    try:
        UISettings(zoom=500)
        assert False, "Should have raised validation error"
    except Exception:
        pass  # expected

    # Invalid theme
    try:
        UISettings(theme="invalid")
        assert False, "Should have raised"
    except Exception:
        pass
