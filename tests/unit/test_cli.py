from typer.testing import CliRunner

from reelcut.cli import app

runner = CliRunner()


def test_help_names_the_app_and_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "reelcut" in result.output


def test_version_flag_prints_name_and_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == "reelcut 0.1.0"
