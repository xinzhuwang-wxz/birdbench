"""Typer CLI：resolve / prompts / run。见 DESIGN §5.5。run 走真机 LiteLLM（需 .env key）。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from birdbench.core import default_prompt
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
    """列出可用 prompt 版本（V0 内置；S12 外置到 prompts/）。"""
    p = default_prompt()
    typer.echo(f"{p.name}\t{p.version}\thash={p.content_hash}")


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
) -> None:
    """跑评测：manifest × models → predictions.jsonl。真机 LiteLLM（需 .env key）。"""
    from birdbench.bench import load_manifest, run_bench
    from birdbench.gateway import LiteLLMGateway
    from birdbench.resolve import Gazetteer

    specs = [ModelSpec(**m) for m in json.loads(models_config.read_text())]
    reg = load_registry()
    items = load_manifest(manifest)
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
        )
    )
    typer.echo(f"{len(recs)} cells → {out}")


if __name__ == "__main__":
    app()
