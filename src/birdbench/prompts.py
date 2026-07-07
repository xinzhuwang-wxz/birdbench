"""prompt 注册表：外部可编辑的版本化 prompt 文件（prompts/<name>.<version>.md）。见 §5.6。

格式：markdown 三段 `## params`(json)/`## system`/`## user`。文件名给 name/version。
prompt 是一等评测轴：bench `--prompts v0,v1` 多选，榜按 (model, prompt) 对比。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from birdbench.schemas import PromptSpec

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
_SECTION = re.compile(r"^##\s+(\w+)\s*$", re.MULTILINE)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _sections(text: str) -> dict[str, str]:
    parts = _SECTION.split(text)  # [pre, name1, body1, name2, body2, ...]
    return {parts[i].lower(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def parse_prompt(text: str, name: str, version: str) -> PromptSpec:
    secs = _sections(text)
    raw = _FENCE.sub("", secs.get("params", "")).strip()
    return PromptSpec(
        name=name,
        version=version,
        content_hash=hashlib.sha256(text.encode()).hexdigest()[:12],
        system=secs.get("system", ""),
        user_template=secs.get("user", ""),
        params=json.loads(raw) if raw else {},
    )


def load_prompt_file(path: str | Path) -> PromptSpec:
    p = Path(path)
    name, version = p.stem.rsplit(".", 1)  # species_id.v0.md → ("species_id", "v0")
    return parse_prompt(p.read_text(), name, version)


def list_prompts(prompts_dir: str | Path = _PROMPTS_DIR) -> list[PromptSpec]:
    d = Path(prompts_dir)
    return [load_prompt_file(f) for f in sorted(d.glob("*.md"))] if d.exists() else []


def load_prompt(
    name: str, version: str = "v0", prompts_dir: str | Path = _PROMPTS_DIR
) -> PromptSpec | None:
    f = Path(prompts_dir) / f"{name}.{version}.md"
    return load_prompt_file(f) if f.exists() else None
