"""S12 gate: prompt 注册表（外部可编辑文件 + 版本化）。"""

from birdbench.prompts import list_prompts, load_prompt, parse_prompt

_SAMPLE = """## params
```json
{"top_k": 3, "cot": true}
```

## system
Sys text here.

## user
User text with JSON.
"""


def test_parse_prompt():
    p = parse_prompt(_SAMPLE, "x", "v9")
    assert p.name == "x" and p.version == "v9"
    assert p.params == {"top_k": 3, "cot": True}
    assert p.system == "Sys text here."
    assert "JSON" in p.user_template
    assert p.content_hash


def test_content_hash_stable():
    h = parse_prompt(_SAMPLE, "x", "v1").content_hash
    assert h == parse_prompt(_SAMPLE, "x", "v1").content_hash


def test_load_committed_default_v0():
    p = load_prompt("species_id", "v0")
    assert p is not None
    assert p.version == "v0"
    assert p.params["cot"] is False and p.params["top_k"] == 5
    assert "COMMON name" in p.system and "JSON" in p.user_template


def test_list_prompts_includes_default():
    assert ("species_id", "v0") in {(p.name, p.version) for p in list_prompts()}


def test_load_missing_returns_none():
    assert load_prompt("nope", "v0") is None
