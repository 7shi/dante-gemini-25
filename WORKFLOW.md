# Workflow

How the Project Gutenberg Italian text becomes the published site: what runs in
what order, what each stage leaves behind, and why the stages are shaped the
way they are. The per-stage detail lives in the READMEs next to the code
([`it/`](it/README.md), [`translate/`](translate/README.md),
[`images/`](images/README.md), [`templates/`](templates/README.md)), each of
which documents its own pipeline; this file is the map between them.

Every stage that calls a model is resumable: re-running after an interruption
continues from where it stopped.

## The stages

| # | Stage | Command | Writes |
|---|-------|---------|--------|
| 1 | Fetch and split the source | `make -C it all split` | `it/{part}/NN.txt` (gitignored) |
| 2 | Segment | `make -C translate segment1` / `segment2` / `segment3` | `translate/segments/{part}.jsonl` |
| 3 | Translate | `make -C translate translate-en` / `translate-ja` | `en.jsonl`, `ja.jsonl` |
| 4 | Reflow mismatched segments | `make -C translate align` | the same JSONL, rewritten in place |
| 5 | Check line counts | `make -C translate check` | nothing (validation) |
| 6 | Expand to per-canto text | `make -C translate convert` | `en/{part}/NN.txt`, `ja/{part}/NN.txt` |
| 7 | Segment summaries | `make -C translate summarize` | `it/{part}.md`, `en/{part}.md`, `ja/{part}.md` |
| 8 | One-line canto summaries | `make -C translate summarize1` | `{it,en,ja}/{part}-1.md` |
| 9 | Trim repetition (rarely) | `make -C translate dedup ARGS='-c inferno:28'` | the `{part}.md` files |
| 10 | Illustrations | `make images` (see [`images/`](images/README.md) to generate them) | `dist/images/` |
| 11 | Build and deploy | `make build`, `make deploy` | `dist/`, the `gh-pages` branch |

Stages 1-2 are run once. Stages 3-4 and 7-8 are the expensive ones. Stage 9 is
for a canto you have judged repetitive, not a pass over the poem - so far no
canto has called for it.

**1. Fetch and split.** [`it/`](it/README.md) downloads `pg1000.txt` and splits
it into one file per canto. Both the download and the split output are
gitignored, so a fresh clone runs this first.

**2. Segment.** `translate/segment_chapters.py` asks the model to split each
canto's lines into translation-sized segments and records the line ranges. The
result is 34 cantos / 126 segments for Inferno and 33 / 125 for each of the
other two canticles.

**3. Translate.** `translate/translate_segments.py` runs once per target
language and writes one record per segment into `en.jsonl` / `ja.jsonl`.
Cantos must be translated in story order with no gaps: each call's context is
built by walking the preceding cantos and collecting their summaries.

**4-5. Reflow and check.** A segment occasionally comes back with the wrong
line count - a line lost, or the whole segment collapsed into prose.
`align_lines.py` redistributes the existing translation over the source's line
count without re-translating; `check.py` validates that every segment's line
count matches across Italian, English and Japanese.

**6. Expand.** `convert.py` writes the per-canto `.txt` files the site is built
from. It overwrites them, which is why it lives in `translate/` rather than the
root `Makefile` - see the regeneration rules below.

**7-8. Summarize.** `summarize_segments.py` writes one paragraph per segment
into `{part}.md`, and `summarize1.py` compresses each canto's paragraphs into
the one line of `{part}-1.md`. Both write Italian, English and Japanese in a
single call as a matched trilingual set (see below).

**9. Dedup.** `dedup_summaries.py` rewrites one canto's Italian summaries to
drop what a later segment restates from an earlier one, then carries the same
edits into English and Japanese. Italian first, because it is the anchor the
other two translate.

**10-11. Illustrate, build and deploy.** [`images/`](images/README.md)
generates the canto illustrations from the English translation and is run on
its own; `make images` only compresses the chosen ones into `dist/`.
`templates/build.py` renders the canto pages, the per-canticle index and
summary pages and the landing page into `dist/`; `make deploy` pushes `dist/`
to `gh-pages`.

## `part/canto/segment` is the spine, and so is the line count

Two things have to stay in agreement for the site to render.

**The segmentation.** `translate/segments/{part}.jsonl` fixes how a canto is
divided, and `templates/build.py` pairs those line ranges with the paragraphs
of `{part}.md`, one per segment. If a canto's boundaries and paragraphs
disagree on how many segments it has, that canto is rendered unsegmented with a
warning. Re-running stage 2 renumbers everything and invalidates the
translations and the summaries alike.

**The line count.** The canto page puts Italian, English and Japanese on the
same row, line by line, so a segment whose translation has the wrong number of
lines does not merely read badly - it shifts every following line out of
alignment. That is what stages 4 and 5 exist for.

## Why the reading page is shaped the way it is

This is a poem, and the workflow is specialised for verse. Two decisions follow
from that.

**Three languages side by side, line by line.** Verse lines are short and
parallel, so the three languages fit in columns and can be read against each
other - which is the point of a translation project. Prose could not be
presented this way, and the site never asks the reader to pick one language.

**The summary comes before the text.** A verse surface is fragmentary: read
line by line, the thread of what is happening is hard to hold. So each canto
page opens with the canto's one-line summary and then presents the text one
segment at a time, each headed by that segment's summary. The summary is not a
substitute for the text but the scaffolding that makes it followable - a
tradeoff worth making here in a way it would not be for prose, where the
sentences carry their own continuity and an interleaved retelling would only
compete with them.

Both decisions are why the summaries are generated as a **matched trilingual
set**. They sit next to each other on the page, so a mismatch between them is
visible in a way an independently written per-language summary never survives.
`summarize_segments.py` therefore writes the Italian summary first, grounded in
the Italian source, and asks for the English and Japanese as strict
translations of it, in one structured call; `summarize1.py` does the same for
the one-line summaries, reading the segment summaries rather than the poem.
Italian is the anchor throughout: `en/` and `ja/`'s summaries translate it, and
`dedup_summaries.py` corrects it first for the same reason.

The model choice follows from the project's premise rather than from cost. The
summaries were first generated with `openai:gpt-5.6-terra` and regenerated with
`google:gemini-2.5-pro`, because a summary written by another model is not this
project's text; the superseded pass is kept in
[`translate/summaries-terra/`](translate/summaries-terra/README.md). `ALIGN_MODEL`
and `DEDUP_MODEL` stay on Terra: reflowing lines and trimming a restatement
edit text rather than author it. See
[`translate/README.md`](translate/README.md#summary-generation-passes).

## What to re-run when something changes

The site is built from the expanded `it/`, `en/`, `ja/` files, never from
`en.jsonl` / `ja.jsonl`, so fixes are made in the expanded files and the
regenerators are the thing to be careful with.

| Changed | Re-run |
|---------|--------|
| one wrong line of a translation | edit `en/{part}/NN.txt` or `ja/{part}/NN.txt` directly, then `make build` |
| a systematic translation issue | fix `en.jsonl` / `ja.jsonl`, `make -C translate convert`, then `make build` - this overwrites every hand-fix in the `.txt` files |
| one canto's one-line summary | delete that canto's line from the three `{part}-1.md` files, re-run `make -C translate summarize1` |
| one segment summary | edit the paragraph in all three `{part}.md` files by hand - `summarize_segments.py` resumes from the first gap, so deleting one paragraph regenerates every segment after it too |
| `translate/segments/{part}.jsonl` | everything downstream (and the corpus is renumbered - see above) |
| templates or static assets | `make build` |

Two traps worth naming:

- **Do not run `make convert` after `make summarize`.** `convert.py` still
  rewrites `en/{part}.md` and `ja/{part}.md` from the JSONL's old, per-language
  `summary` fields, which would clobber the trilingual set with the mismatched
  summaries it replaced.
- **There is no target that wipes the summaries.** A full regeneration is a
  whole-poem LLM run, so starting over means deleting the six `.md` (or six
  `-1.md`) files by hand, deliberately.
