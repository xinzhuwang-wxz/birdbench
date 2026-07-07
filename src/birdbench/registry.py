"""taxonomy registry：从 vendored 快照建可查索引（离线、确定性、stdlib）。见 DESIGN §3, §5.2。

- `species`: speciesCode → 科属种（来自 species.jsonl，11167 种，身份真源）
- `rollup`: 细码(issf 等) → reports_as 种码（rollup.jsonl）
- 精确名索引: 只收 `category ∈ {species, issf}` 的 comName/sciName（issf 经 rollup 落种）；
  slash/spuh/hybrid/form/domestic/intergrade 不进（其 code 不在 species.jsonl）。
- 歧义感知：一个归一化名映射到 >1 个**不同种码** → ambiguous（解析器据此弃答，不 first-win）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "taxonomy"
_SPECIES = _DATA / "species.jsonl"
_ROLLUP = _DATA / "rollup.jsonl"
_RAW = _DATA / "raw" / "ebird_taxonomy.2026-07-04.jsonl"

# 进物种解析索引的类别：species 直接、issf 经 rollup 后处理落种。其余排除（见 DESIGN §5.2）。
_INDEXED_CATEGORIES = frozenset({"species", "issf"})


def normalize(s: str) -> str:
    """归一化：小写、撇号直接去掉、其余标点→空格、压空白。保留 unicode 词字符（中文名不被删）。"""
    s = s.lower().replace("'", "").replace("’", "")
    s = re.sub(r"[^\w ]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


@dataclass(frozen=True)
class Species:
    ebird_code: str
    sci_name: str
    genus: str
    family_sci: str
    family_code: str
    order: str


class Registry:
    def __init__(
        self,
        species: dict[str, Species],
        rollup: dict[str, str],
        com_index: dict[str, set[str]],
        sci_index: dict[str, set[str]],
        code_alias: dict[str, set[str]] | None = None,
    ) -> None:
        self.species = species
        self.rollup = rollup
        self._com = com_index
        self._sci = sci_index
        self._code_alias = code_alias or {}  # norm(4字母码) → set[code]（唯一命中才认）

    def resolve_to_species(self, code: str) -> str:
        """把任意 code（含 issf 细码）收敛到种码（rollup 后处理）。"""
        return self.rollup.get(code, code)

    def taxonomy_of(self, code: str) -> Species | None:
        """给 code（可为 issf）→ Species（科属种）。非种且无 rollup → None。"""
        return self.species.get(self.resolve_to_species(code))

    def _exact(self, index: dict[str, set[str]], name: str) -> tuple[str | None, bool]:
        codes = index.get(normalize(name))
        if not codes:
            return None, False
        species_codes = {self.resolve_to_species(c) for c in codes}
        if len(species_codes) == 1:
            return next(iter(species_codes)), False
        return None, True  # 多义 → 弃答

    def exact_common(self, name: str) -> tuple[str | None, bool]:
        """英文俗名 → (种码, ambiguous)。"""
        return self._exact(self._com, name)

    def exact_scientific(self, name: str) -> tuple[str | None, bool]:
        """学名 → (种码, ambiguous)。"""
        return self._exact(self._sci, name)

    def by_code_alias(self, token: str) -> tuple[str | None, bool]:
        """4 字母缩写码(com/sciNameCodes) → (种码, ambiguous)。多义(CACA→21 种)→ 弃答。"""
        return self._exact(self._code_alias, token)


def load_registry(
    species_path: Path = _SPECIES,
    rollup_path: Path = _ROLLUP,
    raw_path: Path = _RAW,
) -> Registry:
    species: dict[str, Species] = {}
    with species_path.open() as f:
        for line in f:
            r = json.loads(line)
            species[r["ebird_code"]] = Species(
                ebird_code=r["ebird_code"],
                sci_name=r["sci_name"],
                genus=r["genus"],
                family_sci=r["family_sci"],
                family_code=r["family_code"],
                order=r["order"],
            )

    rollup: dict[str, str] = {}
    with rollup_path.open() as f:
        for line in f:
            r = json.loads(line)
            rollup[r["ebird_code"]] = r["reports_as_ebird_code"]

    com: dict[str, set[str]] = {}
    sci: dict[str, set[str]] = {}
    code_alias: dict[str, set[str]] = {}
    with raw_path.open() as f:
        for line in f:
            r = json.loads(line)
            if r.get("category") not in _INDEXED_CATEGORIES:
                continue
            code = r["speciesCode"]
            if r.get("comName"):
                com.setdefault(normalize(r["comName"]), set()).add(code)
            if r.get("sciName"):
                sci.setdefault(normalize(r["sciName"]), set()).add(code)
            for tok in (*r.get("comNameCodes", []), *r.get("sciNameCodes", [])):
                code_alias.setdefault(normalize(tok), set()).add(code)

    return Registry(species, rollup, com, sci, code_alias)
