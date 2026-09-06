# Dante's Divine Comedy Translation with Gemini 2.5 Pro

This project translates Dante's Divine Comedy from Italian to English and Japanese using Google's Gemini 2.5 Pro model. Unlike previous multilingual explorations, this project focuses specifically on English and Japanese translations.

**[Read online](https://7shi.github.io/dante-gemini-25/)** — each canto as a line-by-line Italian/English/Japanese page, split into segments with the segment summary above each one, plus, per canticle (Inferno/Purgatorio/Paradiso), an index page with the Italian/English/Japanese one-line summary of every canto and a summary page with the segment summaries, side by side.

> [!NOTE]
> All translations in this repository are machine-generated (Gemini 2.5 Pro) and have not been reviewed or corrected by a human translator.
> Errors and mistranslations are present throughout.
> These files are provided as-is for reference and study purposes only.

## Workflow

[WORKFLOW.md](WORKFLOW.md) is the developer's map of the whole route — source
text, segmentation, translation, summaries, site — and of why the stages are
shaped the way they are. Each stage's own README documents its pipeline in
detail.

## Source Text

Original Italian text from [Project Gutenberg](https://www.gutenberg.org/ebooks/1000).

See [it/README.md](it/README.md) and [translate/README.md](translate/README.md) for the pipeline that turns this source text into the per-segment JSONL files consumed below.

## Shared Code

[`common/`](common/) holds Python modules shared between `templates/build.py` and the `translate/` pipeline (e.g. reading/writing the `{part}.md` summary format). It's an installable package (see `[build-system]` / `[tool.hatch.build.targets.wheel]` in `pyproject.toml`), so after `uv sync` it's importable as `common.<module>` from any directory in the project, no path juggling needed.

## Output Structure

Each of `it/`, `en/`, `ja/` has the same layout:

```
{lang}/                      # it/, en/, or ja/
├── inferno/
│   ├── 01.txt              # Canto 1 text (translation, for en/ja)
│   ├── 02.txt              # Canto 2 text
│   └── ...
├── purgatorio/
│   └── ...
├── paradiso/
│   └── ...
├── inferno.md              # Inferno segment summaries by canto
├── purgatorio.md           # Purgatorio segment summaries by canto
├── paradiso.md             # Paradiso segment summaries by canto
├── inferno-1.md            # Inferno one-line summaries by canto
├── purgatorio-1.md         # Purgatorio one-line summaries by canto
└── paradiso-1.md           # Paradiso one-line summaries by canto
```

The `{part}.md` and `{part}-1.md` files are edited directly, not generated
from `en.jsonl`/`ja.jsonl`: `translate/summarize_segments.py` regenerates
`{part}.md` (one paragraph per segment) and `translate/summarize1.py`
derives `{part}-1.md` (one line per canto) from it, both as a matched
it/en/ja trilingual set grounded in the Italian source, in one structured
LLM call per segment/canto. See [translate/README.md](translate/README.md)
for details; both are resumable via `make -C translate summarize` /
`summarize1`.

If a segment's translation is wrong, edit `en/{part}/NN.txt` or
`ja/{part}/NN.txt` directly, or, for the source of a systematic issue, fix
it in `en.jsonl`/`ja.jsonl` (see [translate/README.md](translate/README.md#fix-up-tools))
and re-run `make -C translate convert` to propagate it into those `.txt`
files. To fix a specific canto's one-line summary, delete that canto's
entry from the `{part}-1.md` files and re-run `summarize1.py`, which
regenerates only that gap; `summarize_segments.py` resumes from the first
gap onward instead, so fixing one segment's summary means regenerating
every segment after it too (see [translate/README.md](translate/README.md)).

## Proper Nouns

[`PROPER_NOUNS.tsv`](PROPER_NOUNS.tsv) lists the proper nouns appearing in the
texts as an `Italian` / `English` / `Japanese` table, aligned from the
line-parallel `it/`, `en/` and `ja/` files. `translate/translate_segments.py`
supports feeding such a table into its translation prompts via
`--proper-nouns`, but its default path doesn't point at this file, and no past
translation run has passed `--proper-nouns` explicitly - so this table has not
yet been used to enforce transliteration consistency during translation.

[`ja/NAMES.md`](ja/NAMES.md) (written in Japanese) records the naming
conventions for the Japanese translation - Italian readings for Italians,
established Japanese readings for everyone else, Arabic numerals for regnal
numbers - together with the list of spelling variants to be unified.

## Illustrations

See [images/README.md](images/README.md) for the pipeline that generates chapter illustrations from the English translations above using Gemini's image generation.

The generated image data is distributed separately via [Releases](https://github.com/7shi/dante-gemini-25/releases) (along with `en.jsonl` and `ja.jsonl`).

## Translation Quality

The translation data has been segmented to match the Italian source text structure. `make -C translate check` validates that every segment's line count matches across Italian, English, and Japanese versions.

A segment occasionally comes back from `translate_segments.py` with the wrong line count - anything from a couple of lines off to the whole segment collapsed into one line of prose. `translate/align_lines.py` fixes this without re-translating: see [translate/README.md](translate/README.md#fix-up-tools).

## Build and deploy

See [templates/README.md](templates/README.md) for the build/deploy steps.

The site is built directly from the expanded `it/`, `en/` and `ja/` files (not from `en.jsonl` / `ja.jsonl`), since translation and summary fixes are made in those expanded files directly. Re-running `make -C translate convert` regenerates `en/` / `ja/`'s translation `.txt` files from the jsonl and would overwrite any hand-fix made directly in them, which is why it lives in `translate/` rather than the root `Makefile`.

## Related Previous Projects

- [dante-gemini](https://github.com/7shi/dante-gemini) - A multilingual exploration of Dante's Divine Comedy using Gemini 1.0 Pro, featuring detailed linguistic analysis of the opening lines in Italian, English, Hindi, Chinese, Ancient Greek, Arabic, Bengali and other languages with word-by-word breakdowns, grammatical details, and etymologies.
- [dante-la-el](https://github.com/7shi/dante-la-el) - Originally started as a project to transcribe historical Latin and Ancient Greek translations of Dante's Divine Comedy, but evolved into an early LLM experimentation project when AI became the primary focus, exploring computational linguistic analysis methods.
