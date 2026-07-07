"""S8 gate: Typer CLI（resolve / prompts，离线可测）。"""

from typer.testing import CliRunner

from birdbench.cli import app

runner = CliRunner()


def test_resolve_command():
    result = runner.invoke(app, ["resolve", "Cooper's Hawk"])
    assert result.exit_code == 0
    assert "coohaw" in result.stdout
    assert "Accipitridae" in result.stdout
    assert "EXACT_COM" in result.stdout


def test_resolve_hallucination_abstains():
    result = runner.invoke(app, ["resolve", "Sparg de Cooper"])
    assert result.exit_code == 0
    assert "ABSTAIN" in result.stdout
    assert '"species_code": null' in result.stdout


def test_prompts_command():
    result = runner.invoke(app, ["prompts"])
    assert result.exit_code == 0
    assert "species_id" in result.stdout and "v0" in result.stdout
