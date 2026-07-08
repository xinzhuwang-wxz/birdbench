"""V1-5 gate: Gradio Web 壳的 handler（离线，不需 gradio）；build_app 需 gradio 则跳过。"""

import pytest

from birdbench.web import identify_handler, leaderboard_handler, sample_predictions_jsonl


def test_build_app_if_gradio():
    pytest.importorskip("gradio")
    from birdbench.web import build_app

    assert build_app() is not None


async def test_identify_handler_demo(tmp_path):
    p = tmp_path / "bird.jpg"
    p.write_bytes(b"img")
    md, tbl, trace = await identify_handler(str(p), "fake/demo")
    assert "Northern Cardinal" in md and "norcar" in md  # demo fake → 解析出科属种
    assert len(tbl) >= 1
    # 完整 trace：模型最初输出 → 提取 → 逐阶解析（含具体信息）
    assert "模型最初输出" in trace and "Northern Cardinal" in trace  # 原始输出
    assert "提取的候选" in trace  # parse
    assert "解析梯子" in trace and "EXACT_COM" in trace and "norcar" in trace  # 逐阶+结果


async def test_identify_handler_no_image_no_crash():
    md, tbl, trace = await identify_handler(None, "fake/demo")
    assert "请先上传" in md and tbl == [] and trace == ""


async def test_identify_handler_temp_thinking_pass_through(tmp_path):
    p = tmp_path / "bird.jpg"
    p.write_bytes(b"img")
    md, _, trace = await identify_handler(str(p), "fake/demo", temperature=0.7, thinking=True)
    assert "Northern Cardinal" in md and "EXACT_COM" in trace  # 新参数不破坏路径


def test_trace_resolve_steps():
    from birdbench.registry import load_registry
    from birdbench.resolve import trace_resolve

    reg = load_registry()
    steps, outcome = trace_resolve("Mallard", reg)
    assert outcome.matched_species_code == "mallar3"
    assert steps[0]["stage"] == "NORMALIZE" and steps[0]["result"] == "mallard"
    fired = [s for s in steps if s["result"] == "mallar3"]
    assert fired and fired[-1]["stage"] == "EXACT_COM"  # 命中阶 + 结果码正确
    # 未命中的名 → 弃答，梯尾 ABSTAIN
    steps2, out2 = trace_resolve("Domestic Duck", reg)
    assert out2.matched_species_code is None and steps2[-1]["stage"] == "ABSTAIN"


def test_gateway_temperature_and_thinking_wiring():
    from birdbench.web import _gateway

    _, spec = _gateway("volcengine/doubao-seed-2-0-lite-260428", 0.3, True)
    assert spec.params["temperature"] == 0.3
    assert spec.params["extra_body"]["thinking"]["type"] == "enabled"  # doubao 开
    _, spec = _gateway("volcengine/doubao-seed-2-0-lite-260428", 0.0, False)
    assert spec.params["extra_body"]["thinking"]["type"] == "disabled"  # doubao 关(默认)
    _, spec = _gateway("dashscope/qwen3-vl-plus", 0.5, True)
    assert spec.params["temperature"] == 0.5
    assert "extra_body" not in spec.params  # 非 doubao 无 thinking 字段


def test_leaderboard_handler(tmp_path):
    f = tmp_path / "p.jsonl"
    f.write_text(sample_predictions_jsonl())
    html = leaderboard_handler(str(f))
    assert "Leaderboard" in html and "m-good" in html


def test_leaderboard_handler_empty_no_crash():
    assert "请上传" in leaderboard_handler(None)
