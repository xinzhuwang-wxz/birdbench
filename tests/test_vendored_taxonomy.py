"""S0 gate: vendored bird-taxonomy 快照存在且形状正确（stdlib-only，无需第三方依赖）。"""

import json
from pathlib import Path

TAXO = Path(__file__).resolve().parent.parent / "data" / "taxonomy"
RAW = TAXO / "raw" / "ebird_taxonomy.2026-07-04.jsonl"


def _first(path: Path) -> dict:
    with path.open() as f:
        return json.loads(f.readline())


def _count(path: Path) -> int:
    with path.open() as f:
        return sum(1 for _ in f)


def test_vendored_files_present_with_expected_counts():
    assert _count(TAXO / "species.jsonl") == 11167
    assert _count(TAXO / "rollup.jsonl") == 4120
    assert _count(TAXO / "avibase_map.jsonl") == 8785
    assert _count(RAW) == 17891


def test_species_record_has_identity_and_taxonomy_fields():
    rec = _first(TAXO / "species.jsonl")
    for key in ("ebird_code", "sci_name", "genus", "family_sci", "family_code", "order"):
        assert key in rec, f"species.jsonl missing {key}"


def test_raw_snapshot_carries_resolution_keys():
    # raw 快照是解析主索引：俗名 + 学名 + 物种码 + 缩写码
    rec = _first(RAW)
    for key in ("speciesCode", "comName", "sciName", "comNameCodes", "sciNameCodes"):
        assert key in rec, f"raw snapshot missing {key}"


def test_rollup_maps_finer_taxa_to_species():
    rec = _first(TAXO / "rollup.jsonl")
    assert "ebird_code" in rec and "reports_as_ebird_code" in rec
