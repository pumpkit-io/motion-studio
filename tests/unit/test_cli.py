from typer.testing import CliRunner

from motion_studio.cli import app

runner = CliRunner()


def test_help_names_the_app_and_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "motion-studio" in result.output


def test_version_flag_prints_name_and_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == "motion-studio 0.1.0"


def test_help_describes_talk_and_product_videos() -> None:
    result = runner.invoke(app, ["--help"])
    text = " ".join(result.output.split())
    assert "talking-head videos" in text
    assert "product videos" in text
    assert "screen recordings" in text
