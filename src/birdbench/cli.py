"""Typer CLI：resolve / prompts / run。见 DESIGN §5.5。run 走真机 LiteLLM（需 .env key）。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from birdbench.registry import load_registry
from birdbench.resolve import resolve as resolve_name
from birdbench.schemas import ModelSpec

app = typer.Typer(help="birdbench — 多模型多模态 API 鸟类识别评测台", no_args_is_help=True)


@app.command("resolve")
def resolve_cmd(name: str) -> None:
    """把一个鸟名解析成 eBird speciesCode + 科属种。"""
    reg = load_registry()
    r = resolve_name(name, reg)
    tax = reg.taxonomy_of(r.matched_species_code) if r.matched_species_code else None
    typer.echo(
        json.dumps(
            {
                "input": name,
                "stage": r.stage_fired,
                "species_code": r.matched_species_code,
                "taxonomy": (
                    {
                        "order": tax.order,
                        "family": tax.family_sci,
                        "genus": tax.genus,
                        "scientific_name": tax.sci_name,
                    }
                    if tax
                    else None
                ),
                "ambiguous": r.ambiguous,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("prompts")
def prompts_cmd() -> None:
    """列出可用 prompt 版本（prompts/ 目录，同事可编辑）。"""
    from birdbench.prompts import list_prompts

    for p in list_prompts():
        typer.echo(f"{p.name}\t{p.version}\thash={p.content_hash}\t{p.params}")


@app.command("report")
def report_cmd(
    predictions: Path,
    out: Path = typer.Option(Path("runs/report.html"), "--out"),
) -> None:
    """从 predictions.jsonl 生成 HTML 榜 + leaderboard.json。"""
    from birdbench.report import load_predictions, write_report

    rows = write_report(load_predictions(predictions), out)
    typer.echo(f"{len(rows)} models → {out}")


@app.command("run")
def run_cmd(
    manifest: Path,
    models_config: Path = typer.Option(..., "--models", help="models JSON 列表"),
    out: Path = typer.Option(Path("runs/predictions.jsonl"), "--out"),
    cache: Path = typer.Option(Path(".cache"), "--cache"),
    run_id: str = typer.Option("run", "--run-id"),
    normalizer_model: str = typer.Option(
        "", "--normalizer-model", help="轻量文字模型 id，启用 LLM 名字归一化尾巴（V1-8）"
    ),
) -> None:
    """跑评测：manifest × models → predictions.jsonl。真机 LiteLLM（需 .env key）。"""
    from birdbench.bench import load_manifest, run_bench
    from birdbench.gateway import LiteLLMGateway
    from birdbench.resolve import Gazetteer

    specs = [ModelSpec(**m) for m in json.loads(models_config.read_text())]
    reg = load_registry()
    items = load_manifest(manifest)
    normalizer = None
    if normalizer_model:
        from birdbench.llm_normalize import make_normalizer

        nspec = ModelSpec(
            alias=normalizer_model,
            model_id=normalizer_model,
            provider=normalizer_model.split("/")[0],
            params={"temperature": 0},
        )
        normalizer = make_normalizer(LiteLLMGateway([nspec]), nspec)
    recs = asyncio.run(
        run_bench(
            items,
            specs,
            gateway=LiteLLMGateway(specs),
            registry=reg,
            gazetteer=Gazetteer(),
            run_id=run_id,
            cache_dir=cache,
            out_path=out,
            normalizer=normalizer,
        )
    )
    typer.echo(f"{len(recs)} cells → {out}")


@app.command("web")
def web_cmd() -> None:
    """启动 Gradio Web 壳（产品端拖拽台）。默认 demo(不花钱)；BIRDBENCH_REAL=1 真机。"""
    from birdbench.web import main

    main()


@app.command("identify")
def identify_cmd(
    image: Path,
    model_id: str = typer.Option("openai/gpt-4o", "--model", help="litellm model id"),
    alias: str = typer.Option("", "--alias"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """丢一张图 → 科属种 + top-k + 解析透明度 + 成本（产品端）。真机 LiteLLM（需 .env key）。"""
    from birdbench.core import identify
    from birdbench.gateway import LiteLLMGateway

    media = {".png": "image/png", ".webp": "image/webp"}.get(image.suffix.lower(), "image/jpeg")
    spec = ModelSpec(alias=alias or model_id, model_id=model_id, provider=model_id.split("/")[0])
    res = asyncio.run(
        identify(
            image.read_bytes(),
            spec,
            gateway=LiteLLMGateway([spec]),
            registry=load_registry(),
            media_type=media,
        )
    )
    if as_json:
        typer.echo(res.model_dump_json(indent=2))
        return
    if res.abstain:
        typer.echo(f"[{res.model_alias}] 弃答: {res.abstain_reason}")
        return
    typer.echo(f"[{res.model_alias}] {res.common_name}  ({res.species_code})")
    typer.echo(f"  目/科/属/种: {res.order} / {res.family} / {res.genus} / {res.scientific_name}")
    typer.echo(f"  解析: {res.resolution_stage} score={res.resolution_score:.2f}")
    if res.field_marks:
        typer.echo(f"  依据: {res.field_marks}")
    for c in res.candidates[:5]:
        typer.echo(f"    - {c.common_name} [{c.rank_hint}] conf={c.confidence} → {c.species_code}")
    typer.echo(
        f"  成本 ${res.cost_usd} · 延迟 {res.latency_ms:.0f}ms · tokens {res.total_tokens} · "
        f"model={res.model_resolved}"
    )


if __name__ == "__main__":
    app()
