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
    md, tbl = await identify_handler(str(p), "fake/demo")
    assert "Northern Cardinal" in md and "norcar" in md  # demo fake → 解析出科属种
    assert len(tbl) >= 1


async def test_identify_handler_no_image_no_crash():
    md, tbl = await identify_handler(None, "fake/demo")
    assert "请先上传" in md and tbl == []


async def test_identify_handler_temp_thinking_pass_through(tmp_path):
    p = tmp_path / "bird.jpg"
    p.write_bytes(b"img")
    md, _ = await identify_handler(str(p), "fake/demo", temperature=0.7, thinking=True)
    assert "Northern Cardinal" in md  # 新参数不破坏路径


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
