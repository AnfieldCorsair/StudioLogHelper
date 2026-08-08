from .translator import Translator, LANGS, DEFAULT_LANG

# compat global for old code
_translator = Translator(DEFAULT_LANG)

def set_lang(code: str):
    _translator.set_lang(code)

def get_lang() -> str:
    return _translator.get_lang()

def tr(key: str, **kwargs) -> str:
    return _translator.tr(key, **kwargs)

__all__ = ["Translator", "LANGS", "DEFAULT_LANG", "set_lang", "get_lang", "tr"]
