import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import core


def test_exported_message_with_markdown_headings_and_rules_not_split():
    text = '''--- #4 МОДЕЛЬ ---------------------------------------------------------
Понял вас.

---

### Пример структуры лога чата (chat_log.json)

```json
{"messages": [{"role": "user", "text": "hi"}]}
```

#### 1. Python

```python
print("--- Обработка файла: x ---")
```

#### 2. Node.js

```javascript
console.log(`ID Чата: ${data.chat_id}`);
```
'''
    chat = core.parse_text_log(text, "clean.txt")
    assert len(chat.messages) == 1
    assert chat.messages[0].role == "model"
    assert "#### 1. Python" in chat.messages[0].text
    assert "#### 2. Node.js" in chat.messages[0].text
