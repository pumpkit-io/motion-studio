from pathlib import Path

import pytest

import reelcut.lang
from reelcut.analysis import ClipInfo, Span, TranscribedWord, analyse_transcript
from reelcut.config import Config
from reelcut.errors import UserError
from reelcut.lang import available_languages, load_language

MINIMAL_SPANISH = """
code = "es"
name = "Español"

[asr]
initial_prompt = "Eh, este, o sea, pues... mmm, bueno."

[fillers]
hard = ["eh", "mmm"]
soft = ["o sea"]
soft_at_start = ["pues"]
"""


def test_english_and_italian_ship_with_the_guide_prompts() -> None:
    assert available_languages() == ["en", "it"]
    en, it = load_language("en"), load_language("it")
    assert en.asr.initial_prompt == "Umm, so, uh, I was like, hmm, thinking... you know, um, yeah."
    assert it.asr.initial_prompt.startswith("Ehm, allora, cioè, eh, stavo tipo pensando")
    assert "you know" in en.fillers.soft
    assert "allora" in it.fillers.soft_at_start
    assert en.captions.max_chars_per_page > 0
    assert "il" in it.captions.keep_with_next


def test_a_third_language_needs_only_its_data_file(tmp_path: Path) -> None:
    (tmp_path / "es.toml").write_text(MINIMAL_SPANISH, encoding="utf-8")
    dirs = [reelcut.lang.LANG_DIR, tmp_path]

    spanish = load_language("es", dirs)
    words = [
        TranscribedWord(text=t, start=0.5 + i * 0.3, end=0.75 + i * 0.3)
        for i, t in enumerate(["Pues,", "eh,", "es,", "o", "sea,", "fácil."])
    ]
    clip = ClipInfo(id="c1", role="aroll", source="raw/a.mov", duration_s=3.0)
    result = analyse_transcript(clip, words, [Span(start=0.0, end=3.0)], spanish)

    assert available_languages(dirs) == ["en", "es", "it"]
    assert result.language is not None
    assert result.language.code == "es"
    assert [w.filler for w in result.words] == ["soft", "hard", None, "soft", "soft", None]
    assert result.utterances[0].complete


def test_the_config_accepts_any_language_with_a_data_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "es.toml").write_text(MINIMAL_SPANISH, encoding="utf-8")
    monkeypatch.setattr(reelcut.lang, "LANG_DIR", tmp_path)

    assert Config.model_validate({"defaults": {"language": "es"}}).defaults.language == "es"
    assert Config.model_validate({"defaults": {"language": "auto"}}).defaults.language == "auto"
    with pytest.raises(ValueError, match="no language data for 'fr'"):
        Config.model_validate({"defaults": {"language": "fr"}})


def test_an_unknown_language_names_the_available_ones() -> None:
    with pytest.raises(UserError, match=r"no language data for 'fr' \(available: en, it\)"):
        load_language("fr")


def test_a_language_file_must_declare_its_own_code(tmp_path: Path) -> None:
    (tmp_path / "pt.toml").write_text(MINIMAL_SPANISH, encoding="utf-8")

    with pytest.raises(UserError, match="declares code 'es'"):
        load_language("pt", [tmp_path])
