"""
Extract proper nouns from this repository's own English/Japanese
translations, one row per translated line, and aggregate them into a
`proper_noun.tsv` in the same format as dante-corpus's own
`proper_noun/proper_noun.tsv` - but built from the translations instead of
the Italian original.

This is a straight port of dante-corpus's `proper_noun/proper_noun.py` +
`proper_noun/aggregate.py` onto a different text source: the canto's lines
are read directly from `../{lang}/{part}/NN.txt` (the finished per-canto
translation files this repository already produces via `convert.py`) rather
than through the `dante_corpus` API, and the target language named in the
prompt is English or Japanese instead of Italian. Everything else - the
per-line, verbatim-match extraction with an LLM, one call per
`--block-size`-line group, and the aggregation into one row per distinct
name - works exactly as it does there.

Output, written beside this script:
- `proper_noun/<lang>/<canticle>/<NN>.tsv` (+ `.log`): one row per processed
  line, `line_number<TAB>noun<TAB>noun...`, matching dante-corpus's per-canto
  format. A missing row means the line is not processed yet - the resume
  mechanism.
- `proper_noun/<lang>/proper_noun.tsv`: one row per distinct name,
  `Name<TAB>i:canto:line<TAB>pu:canto:line<TAB>pa:canto:line...`, rebuilt
  from every per-canto file whenever this script runs (or on its own with
  `--aggregate-only`).

    uv run proper_noun.py -l en -m openai:gpt-5.6-terra inferno
    uv run proper_noun.py -l ja --aggregate-only inferno purgatorio paradiso
"""

import argparse
import time
from pathlib import Path
from typing import List, NamedTuple, Tuple
from collections import defaultdict

import dante_corpus.api as corpus_api
from llm7shi import Client
from llm7shi.statusline import StatusLine

SCRIPT_DIR = Path(__file__).resolve().parent
TRANSLATION_ROOT = SCRIPT_DIR.parent  # ../en, ../ja live beside this repo's root
PROPER_NOUN_DIR = SCRIPT_DIR / "proper_noun"

LANG_NAMES = {"en": "English", "ja": "Japanese"}
CANTICLE_ABBREV = {"inferno": "i", "purgatorio": "pu", "paradiso": "pa"}

DEFAULT_BLOCK_SIZE = 3


# ============================================================================
# Logging
# ============================================================================

_log_file = None


def log_print(*args, **kwargs):
    """Print to log file only"""
    if _log_file:
        print(*args, **kwargs, file=_log_file)
        _log_file.flush()


def notify(ui: StatusLine, text: str, error: bool = False) -> None:
    (ui.stream.error if error else ui.log)(text)
    log_print(text)


# ============================================================================
# Shared parsing/loading helpers
# ============================================================================

class Line:
    """A single line of translated text, read directly from a per-canto .txt file."""

    def __init__(self, full_text: str, line_num: int):
        self.full_text = full_text
        self.line_num = line_num

    def __repr__(self):
        return f"Line({self.full_text!r}, line_num={self.line_num})"


def load_lines(lang: str, canticle: str, canto: int) -> List[Line]:
    """Load a canto's translated lines directly from `../{lang}/{canticle}/NN.txt`."""
    path = TRANSLATION_ROOT / lang / canticle / f"{canto:02d}.txt"
    texts = path.read_text(encoding="utf-8").splitlines()
    return [Line(text, i) for i, text in enumerate(texts, 1)]


def pending_groups(lines: List[Line], rows: dict, block_size: int) -> List[List[Line]]:
    """
    The line groups still to ask the LLM about: each `block_size`-line
    block's lines that have no row yet, split into contiguous runs. See
    dante-corpus's `proper_noun.py` for the full rationale - ported
    unchanged.
    """
    groups: List[List[Line]] = []
    for block in chunk_lines(lines, block_size):
        run: List[Line] = []
        for line in block:
            if line.line_num in rows:
                if run:
                    groups.append(run)
                    run = []
            else:
                run.append(line)
        if run:
            groups.append(run)
    return groups


def line_range(lines: List[Line]) -> str:
    """`first-last` for a block of lines, the number alone for a single one."""
    first, last = lines[0].line_num, lines[-1].line_num
    return str(first) if first == last else f"{first}-{last}"


def chunk_lines(lines: List[Line], block_size: int) -> List[List[Line]]:
    return [lines[i:i + block_size] for i in range(0, len(lines), block_size)]


def normalize(text: str) -> str:
    """Casefolded text with apostrophe/quote variants unified, for locating a
    model-reported noun inside its line."""
    return text.translate(str.maketrans("’‘`´", "''''")).lower()


def find_verbatim(noun: str, line: str) -> str | None:
    """The substring of `line` that `noun` names, spelled as the line spells
    it, or None when the model's noun does not occur in the line at all."""
    pos = normalize(line).find(normalize(noun))
    if pos < 0:
        return None
    return line[pos:pos + len(noun)]


# ============================================================================
# Extraction (one LLM call per group of consecutive lines)
# ============================================================================

class LineRow(NamedTuple):
    line: Line
    nouns: List[str]


PROMPT_TEMPLATE = """Below are {n} consecutive line(s) of the {lang_name} translation of Dante's Divine Comedy,
each prefixed by its line number in the canto.

For each line, list the proper nouns it contains, in the order they occur.

What counts as a proper noun (collect these):
- names of people, mythological or biblical figures, and deities
- names of peoples, families and factions
- place names: cities, regions, countries, rivers, mountains, realms of the afterlife
- names of stars, planets and constellations, and titles of books or works

What is NOT a proper noun (never collect these):
- a periphrasis, epithet or metaphor standing for a named person, even when it
  clearly refers to one. This task collects names only, not entities.
- common nouns that merely happen to be capitalized (line-initial capitals, or
  words capitalized for emphasis), and pronouns of any kind

Spell every noun exactly as the line spells it (same letters, same accents,
diacritics and capitalization), so it can be found in the line verbatim. Give
a multi-word name as one entry; list nothing for a line that has no proper noun.

{lang_name} lines:
{numbered}

Output exactly {n} row(s), one per {lang_name} line above, in the order shown. Each row is
that line's number followed by the nouns found in it, all separated by TAB characters
(e.g. "7<TAB>Virgil<TAB>Rome" for a line with two, "8" alone for a line with none).
Output nothing else: no header, no commentary, no code fence, no empty rows."""


class BlockClient(Client):
    """The run's LLM client, with this script's mechanical checks folded
    into the retry loop `llm7shi.Client` already runs. Ported unchanged from
    dante-corpus's `proper_noun.py`."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.lines: List[Line] = []
        self.rows: List[List[str]] | None = None
        self.problem = ""

    def should_retry(self, resp, schema=None) -> str | None:
        self.rows, self.problem = None, ""
        reason = super().should_retry(resp, schema)
        if reason is not None:
            self.problem = reason
            return reason
        self.rows, self.problem = validate_group(resp.text, self.lines)
        return self.problem or None


def validate_group(text: str, lines: List[Line]) -> Tuple[List[List[str]], str] | Tuple[None, str]:
    """Parse the model's TSV reply and check it mechanically against the
    group's lines. Ported unchanged from dante-corpus's `proper_noun.py`."""
    expected = [line.line_num for line in lines]
    got: List[int] = []
    fields: List[List[str]] = []
    for row in text.strip().splitlines():
        row = row.strip()
        if not row or row.startswith('```'):
            continue
        number, *nouns = (field.strip() for field in row.split('\t'))
        if not number.isdigit():
            return None, f"row {row!r} does not start with a line number"
        got.append(int(number))
        fields.append(nouns)
    if got != expected:
        return None, f"line numbers {got} do not match the group's lines {expected}"

    rows: List[List[str]] = []
    for line, found in zip(lines, fields):
        nouns: List[str] = []
        for noun in found:
            if not noun:
                return None, f"line {line.line_num}: empty proper noun"
            verbatim = find_verbatim(noun, line.full_text)
            if verbatim is None:
                return None, (f"line {line.line_num}: proper noun {noun!r} does not occur in "
                              f"the line {line.full_text!r}")
            if verbatim not in nouns:
                nouns.append(verbatim)
        rows.append(nouns)
    return rows, ""


def extract_group(ui: StatusLine, client: BlockClient, lang_name: str, lines: List[Line],
                  index: int, total: int) -> List[List[str]] | None:
    n = len(lines)
    numbered = '\n'.join(f"{line.line_num} {line.full_text}" for line in lines)
    prompt = PROMPT_TEMPLATE.format(n=n, numbered=numbered, lang_name=lang_name)

    ui.log("")
    notify(ui, f"Group {index}/{total}: line(s) {line_range(lines)}")
    for line in lines:
        log_print(f"  {line.line_num} {line.full_text}")

    client.lines = lines
    call_started = time.monotonic()
    ui.log("")
    try:
        client(prompt)
    except Exception as e:
        ui.stream.end()
        notify(ui, f"  ✗ LLM call failed after {time.monotonic() - call_started:.1f}s: {e}",
              error=True)
        return None
    ui.stream.end()
    elapsed = time.monotonic() - call_started

    rows = client.rows
    if rows is None:
        notify(ui, f"  ✗ no valid reply ({elapsed:.1f}s): {client.problem}", error=True)
        return None

    log_print(f"  ✓ accepted ({elapsed:.1f}s)")
    for line, nouns in zip(lines, rows):
        log_print(f"    {line.line_num}: {nouns}")
    return rows


# ============================================================================
# TSV I/O (variable-length rows, a missing row = not processed yet)
# ============================================================================

def format_row(line: Line, nouns: List[str]) -> str:
    return '\t'.join([str(line.line_num), *nouns])


def append_rows(texts: List[str], path: Path):
    with open(path, 'a', encoding='utf-8') as f:
        for text in texts:
            f.write(text + '\n')


def rewrite_tsv(rows: dict, path: Path):
    with open(path, 'w', encoding='utf-8') as f:
        for line_num in sorted(rows):
            f.write(rows[line_num] + '\n')


def load_tsv(ui: StatusLine, path: Path, lines: List[Line]) -> Tuple[dict, bool] | None:
    rows: dict = {}
    order: List[int] = []
    for row_num, text in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not text.strip():
            continue
        field = text.split('\t')[0]
        if not field.isdigit() or not 1 <= int(field) <= len(lines):
            notify(ui, f"✗ {path} row {row_num}: {field!r} is not a line number of this "
                  f"canto (1-{len(lines)}) - delete the file to regenerate", error=True)
            return None
        line_num = int(field)
        if line_num in rows:
            notify(ui, f"✗ {path} row {row_num}: line {line_num} appears twice - "
                  f"delete the file to regenerate", error=True)
            return None
        rows[line_num] = text
        order.append(line_num)
    return rows, order == sorted(order)


# ============================================================================
# Pipeline driver
# ============================================================================

def run_canto(args: argparse.Namespace, ui: StatusLine, client: BlockClient, lang_name: str,
              lines: List[Line], tsv_path: Path, rows: dict, in_order: bool,
              prog=None) -> List[LineRow]:
    groups = pending_groups(lines, rows, args.block_size)
    if args.test:
        groups = groups[:1]

    done = 0
    skipped = 0
    total_groups = len(groups)
    disk_max = max(rows, default=0)
    for index, group in enumerate(groups, 1):
        if prog is not None:
            prog.update(group[0].line_num)
        nums = [line.line_num for line in group]

        group_rows = extract_group(ui, client, lang_name, group, index, total_groups)
        if group_rows is None:
            notify(ui, f"✗ Group {index}/{total_groups} left unwritten; rerun to retry", error=True)
            skipped += 1
            log_print()
            continue

        texts = [format_row(line, nouns) for line, nouns in zip(group, group_rows)]
        rows.update(zip(nums, texts))
        if in_order and nums[0] > disk_max:
            append_rows(texts, tsv_path)
        else:
            rewrite_tsv(rows, tsv_path)
            in_order = True
        disk_max = max(rows)
        done += 1
        log_print()

    out = [LineRow(line, rows[line.line_num].split('\t')[1:])
           for line in lines if line.line_num in rows]
    n_nouns = sum(len(row.nouns) for row in out)

    suffix = f" ({done} group(s) extracted)" if done else ""
    tail = f"; {skipped} group(s) left unwritten - rerun to retry" if skipped else ""
    notify(ui, f"✓ Complete: {len(out)}/{len(lines)} lines, {n_nouns} proper noun(s)"
          f"{suffix}{tail}")
    return out


def extract_canto(lang: str, canticle: str, canto: int, args: argparse.Namespace, n_cantos: int,
                  ui: StatusLine, client: BlockClient) -> None:
    out_dir = PROPER_NOUN_DIR / lang / canticle
    out_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = out_dir / f"{canto:02d}.tsv"
    log_path = out_dir / f"{canto:02d}.log"
    lang_name = LANG_NAMES[lang]

    global _log_file
    with open(log_path, 'w', encoding='utf-8') as log_f:
        _log_file = log_f

        log_print(f"=== {canticle.capitalize()} Canto {canto} Proper Nouns "
                  f"({lang_name}, proper_noun.py) ===")
        log_print(f"Model: {args.model}, Temperature: {args.temperature}, Think: {args.think}, "
                  f"Block size: {args.block_size}, Test: {args.test}")
        log_print()

        lines = load_lines(lang, canticle, canto)

        rows: dict = {}
        in_order = True
        if tsv_path.exists():
            loaded = load_tsv(ui, tsv_path, lines)
            if loaded is None:
                return
            rows, in_order = loaded
            if len(rows) == len(lines):
                notify(ui, f"✓ {canticle.capitalize()} {canto}/{n_cantos}: skipped "
                      f"(output file already exists, every line present)")
                return
            notify(ui, f"{len(rows)}/{len(lines)} line(s) on disk - "
                  f"extracting only what is missing")

        label = f"{lang} {canticle.capitalize()} {canto}/{n_cantos}"
        with ui.progress(len(lines), label=label, dual=True) as prog:
            run_canto(args, ui, client, lang_name, lines, tsv_path, rows, in_order, prog)

    ui.log(f"✓ Proper nouns: {tsv_path}")
    ui.log(f"✓ Log: {log_path}")


# ============================================================================
# Aggregation - port of dante-corpus's aggregate.py
# ============================================================================

def aggregate(lang: str) -> None:
    """Combine `proper_noun/<lang>/<canticle>/<NN>.tsv` into one
    `proper_noun/<lang>/proper_noun.tsv`, in the exact format of
    dante-corpus's own `proper_noun/proper_noun.tsv`."""
    occurrences: dict[str, list[tuple[tuple[int, int, int], str]]] = defaultdict(list)

    for canticle_index, (canticle, abbrev) in enumerate(CANTICLE_ABBREV.items()):
        canticle_dir = PROPER_NOUN_DIR / lang / canticle
        if not canticle_dir.is_dir():
            continue
        for tsv_path in sorted(canticle_dir.glob("*.tsv")):
            canto = int(tsv_path.stem)
            for row in tsv_path.read_text(encoding="utf-8").splitlines():
                if not row.strip():
                    continue
                line_num, *nouns = row.split("\t")
                location = f"{abbrev}:{canto}:{line_num}"
                sort_key = (canticle_index, canto, int(line_num))
                for noun in nouns:
                    occurrences[noun].append((sort_key, location))

    out_path = PROPER_NOUN_DIR / lang / "proper_noun.tsv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for name in sorted(occurrences):
            locations = [loc for _, loc in sorted(occurrences[name])]
            f.write("\t".join([name, *locations]) + "\n")

    n_locations = sum(len(v) for v in occurrences.values())
    print(f"{out_path}: {len(occurrences)} name(s), {n_locations} occurrence(s)")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract proper nouns from this repo's own en/ja translations "
                    "(read directly from ../{lang}/{part}/NN.txt) and aggregate them "
                    "into proper_noun/<lang>/proper_noun.tsv, mirroring dante-corpus's "
                    "own proper_noun.py + aggregate.py")
    parser.add_argument("canticles", nargs="+", choices=["inferno", "purgatorio", "paradiso"],
                        help="Cantica name(s)")
    parser.add_argument("-l", "--lang", required=True, choices=["en", "ja"],
                        help="Target language to extract proper nouns from")
    parser.add_argument("-c", "--canto", help=corpus_api.CANTO_SPEC_HELP)
    parser.add_argument("-m", "--model", default="ollama:qwen3.6",
                        help="LLM model to use (default: a local model for smoke-testing; "
                             "real runs should pass e.g. -m openai:gpt-5.6-terra)")
    parser.add_argument("--temperature", type=float, default=1.0, help="LLM temperature (default: 1.0)")
    parser.add_argument("--think", action="store_true", help="Enable LLM thinking (disabled by default)")
    parser.add_argument("-b", "--block-size", type=int, default=DEFAULT_BLOCK_SIZE,
                        help=f"Number of lines per LLM call (default: {DEFAULT_BLOCK_SIZE}); "
                             f"a rerun asks about at most this many, and only missing lines")
    parser.add_argument("--test", action="store_true",
                        help="Process only the first pending group, for a quick local smoke test")
    parser.add_argument("--aggregate-only", action="store_true",
                        help="Skip extraction; just rebuild proper_noun/<lang>/proper_noun.tsv "
                             "from whatever per-canto .tsv files already exist on disk")

    args = parser.parse_args()

    if err := corpus_api.check_canto_spec(args.canticles, args.canto):
        parser.error(err)
    if args.block_size < 1:
        parser.error("--block-size must be at least 1")

    if args.aggregate_only:
        aggregate(args.lang)
        return

    ui = StatusLine()
    client = BlockClient(model=args.model, include_thoughts=args.think, temperature=args.temperature,
                         file=ui.stream, show_params=False, keep_history=False)
    for canticle in args.canticles:
        n_cantos = len(corpus_api.cantos(canticle))
        for canto in corpus_api.select_cantos(canticle, args.canto):
            extract_canto(args.lang, canticle, canto, args, n_cantos, ui, client)

    aggregate(args.lang)


if __name__ == '__main__':
    main()
