# Italian Source Processing Pipeline

This directory holds the pipeline that turns the Italian source text into the
per-segment JSONL files (`inferno.jsonl`, `purgatorio.jsonl`, `paradiso.jsonl`)
consumed by `convert.py` and `summarize1.py`, which also live here.

## Pipeline

1. **Download the source text** (`make` in this directory)

   Fetches `pg1000.txt` from [Project Gutenberg](https://www.gutenberg.org/ebooks/1000).

2. **Split into per-canto files** (`make split`)

   `split_source.py` reads `pg1000.txt` from stdin and writes one text file
   per canto under `inferno/`, `purgatorio/`, and `paradiso/`
   (e.g. `inferno/01.txt`).

3. **Segment each chapter** (`make segment1` / `segment2` / `segment3`)

   `segment_chapters.py` asks an LLM to split each canto's lines into
   translation-sized segments and appends the boundaries to a JSONL file
   (`inferno.jsonl`, `purgatorio.jsonl`, `paradiso.jsonl`).

   ```
   uv run segment_chapters.py -m gemini-2.5-pro -o inferno.jsonl inferno
   ```

4. **Translate segments** (`make translate-en` / `translate-ja`)

   `translate_segments.py` translates each segment from the per-canto `.txt`
   files into the target language, using a proper-noun dictionary and prior
   segments' summaries as context, and writes the result to the root
   `en.jsonl` / `ja.jsonl`.

   ```
   uv run translate_segments.py -o ../en.jsonl inferno purgatorio paradiso -f Italian -t English -m gemini-2.5-pro
   ```

   Chapters must be translated in story order, front to back, with no gaps,
   since each call's "previous story context" is built by walking chapters
   in order and collecting prior summaries.

## Fix-up tools

Run from this directory (`it/`), so the translation files are addressed as
`../en.jsonl` / `../ja.jsonl`, the same as the pipeline commands above.

- **`align_lines.py`** - Some segments come back from translation with the
  wrong line count (a source line lost or a whole segment collapsed into one
  line of prose). This script does not re-translate; it asks the model to
  redistribute the existing translation over the source's line count,
  rewriting the record in place. Without `-s` it finds and fixes every
  segment whose line count doesn't match the source; `make align` (or
  `align-en` / `align-ja`) runs it for both languages.

  ```
  uv run align_lines.py ../en.jsonl -m openai:gpt-5.6-terra
  uv run align_lines.py ../en.jsonl -m openai:gpt-5.6-terra -s inferno:11:3,purgatorio:18:1
  ```

- **`fix_summary.py`** - If a segment's `summary` field is wrong (e.g.
  hallucinated content unrelated to its translation), this regenerates just
  that field from the segment's own translation text, with no other context.

  ```
  uv run fix_summary.py ../ja.jsonl paradiso 8 1 -m gemini-2.5-pro
  ```

After using either fix-up tool, re-run `make convert` / `make summarize1`
(in this directory) to propagate the changes into the generated markdown
files. These regenerate `../en/` and `../ja/` from the JSONL, overwriting
any hand-fix made directly in those expanded files — that overwrite risk is
why `convert.py` / `summarize1.py` and their `make` targets live here rather
than in the root `Makefile`.

## Other files

- `pg1000.txt` - Downloaded Italian source text (gitignored).
- `inferno/`, `purgatorio/`, `paradiso/` - Per-canto Italian text files
  produced by `split_source.py` (gitignored).
- `inferno.jsonl`, `purgatorio.jsonl`, `paradiso.jsonl` - Segment boundaries
  and translations, keyed by part/chapter/segment.
- `convert.py`, `summarize1.py` - Expand `../en.jsonl` / `../ja.jsonl` into
  the per-canto `../en/` / `../ja/` markdown and text files consumed by the
  site build (see the root [README.md](../README.md#output-structure)).
  Run via `make convert` / `make summarize1` in this directory.
- `check.py` - Validates that every segment's line count matches across the
  Italian source, `../en.jsonl`, and `../ja.jsonl`. Run via `make check`.
