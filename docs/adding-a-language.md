# Adding a language

Everything reelcut knows about a language is in one data file, `src/reelcut/lang/<code>.toml`. No code names a language: the transcriber's candidate languages, the config's `language` values, filler tagging, incomplete-utterance detection and caption paging all read the files that exist. This walk-through adds Spanish as `es.toml`.

## 1. Copy the English file

```sh
cp src/reelcut/lang/en.toml src/reelcut/lang/es.toml
```

The file name must be the language's ISO 639-1 code, the code Whisper detects and reports. `load_language` refuses a file whose `code` differs from its name.

## 2. Fill in each section

```toml
# Spanish language data.
code = "es"
name = "Español"

[asr]
# Biases Whisper towards verbatim output, so it keeps the disfluencies it usually drops.
initial_prompt = "Eh, este, o sea, pues... mmm, bueno, eh, sí."

[fillers]
hard = ["eh", "ehm", "mmm", "mm", "em"]
soft = ["o sea", "este", "bueno", "tipo", "en plan"]
soft_at_start = ["pues", "entonces", "vale"]

[utterances]
incomplete_endings = [
    "el", "la", "los", "las", "un", "una", "y", "o", "pero", "porque", "que",
    "de", "a", "en", "con", "por", "para", "del", "al", "es", "son", "mi", "tu", "su",
]

[captions]
max_chars_per_page = 20
keep_with_next = ["el", "la", "los", "las", "un", "una", "y", "o", "de", "a", "en", "que", "no"]
```

What each key does:

| Key | Effect |
|---|---|
| `code`, `name` | The code used in config and EDLs (`language = "es"`), and a display name. |
| `[asr] initial_prompt` | Passed to Whisper as the initial prompt. A sentence full of the language's fillers makes it transcribe them instead of cleaning them up, which is what lets reelcut cut them. |
| `[fillers] hard` | Fillers the resolver removes under the default policy (`drop_fillers = "hard"`). Keep this list to sounds that are never words. |
| `[fillers] soft` | Fillers marked anywhere in an utterance and left to the agent's judgement (the policy `drop_fillers = "hard+soft"` removes them too). Phrases of several words are allowed. |
| `[fillers] soft_at_start` | Marked only at the start of an utterance, where "pues" or "so" is padding rather than meaning. |
| `[utterances] incomplete_endings` | Words a finished sentence does not end on. An utterance that ends on one before a pause of 500 ms or more is marked incomplete, even when Whisper adds a full stop, so abandoned takes lose to their retakes. |
| `[captions] max_chars_per_page` | The most characters on one caption page, spaces included. Lower it for languages with long words. |
| `[captions] keep_with_next` | Short words that never end a caption page, so "de" stays with the word after it. |

Entries are matched case-insensitively with punctuation stripped, so write them in lowercase without punctuation.

## 3. Check it

`tests/unit/test_language_data.py` asserts the shipped language list. Add the new code to `test_english_and_italian_ship_with_the_guide_prompts` (and rename it), then:

```sh
uv run pytest tests/unit/test_language_data.py
uv run reelcut config show        # in a workspace with language = "es" in reelcut.toml
```

A typo in a key name or a missing required key fails loading with the file path and the field (`extra="forbid"` on every section).

Then try it on real footage: record a minute of speech with a few fillers and an abandoned sentence, run `ingest` and `analyze`, and read `analysis/packed.md`. Fillers should be marked, the abandoned sentence should show as incomplete, and `language` in `analysis/c1.json` should be `es`. Tune the lists until they are. `reelcut render` then pages the captions with your caption rules.

## 4. Open a pull request

Add a line to `CHANGELOG.md` under "Unreleased". Nothing else changes: the config schema accepts any code that has a data file, and auto-detection picks among the installed files.
