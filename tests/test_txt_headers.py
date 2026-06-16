import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import core


def test_clean_txt_export_with_model_name_hyphens():
    text = '''--- #1 ПОЛЬЗОВАТЕЛЬ ---------------------------------------------------
ТЕКСТ ПОЛЬЗОВАТЕЛЯ

--- #2 gemini-3.1-pro-preview -----------------------------------------
ОТВЕТ МОДЕЛИ
'''
    chat = core.parse_text_log(text, "clean.txt")
    assert len(chat.messages) == 2
    assert chat.messages[0].role == "user"
    assert chat.messages[0].text == "ТЕКСТ ПОЛЬЗОВАТЕЛЯ"
    assert chat.messages[1].role == "model"
    assert chat.messages[1].text == "ОТВЕТ МОДЕЛИ"


def test_markdown_headings_do_not_split_clean_txt_message():
    text = '''--- #2 gemini-3.1-pro-preview -----------------------------------------
ОТВЕТ

---

### Заголовок внутри Markdown

#### 1. Python

```python
print("hello")
```
'''
    chat = core.parse_text_log(text, "clean.txt")
    assert len(chat.messages) == 1
    assert chat.messages[0].role == "model"
    assert "#### 1. Python" in chat.messages[0].text
