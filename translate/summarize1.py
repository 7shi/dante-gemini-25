"""Generate one-line-per-canto summaries in it/en/ja as a matched trilingual set.

`en/{part}-1.md` and `ja/{part}-1.md` used to be generated independently
from `en.jsonl`/`ja.jsonl`, one language per run - the same mismatch problem
`summarize_segments.py` fixed for the per-segment summaries (see its
docstring). This script does the same for the one-line canto summaries: for
each canto it reads that canto's already-matched it/en/ja segment
paragraphs from `../it/{part}.md`, `../en/{part}.md`, `../ja/{part}.md`
(written by `summarize_segments.py`) and asks the model, in one structured-
output call, for a one-line summary of the whole canto in all three
languages at once - grounded only in those segment summaries, with no old
one-line summary fed in as context. Results are appended to
`../it/{part}-1.md`, `../en/{part}-1.md`, `../ja/{part}-1.md` as they're
produced. If interrupted, re-running loads those files and skips the
cantos already done in all three languages.

Cantos whose it/en/ja segment summaries aren't fully generated yet (see
`summarize_segments.py`) are skipped for now rather than erroring, so this
can be run incrementally alongside it.
"""

import argparse
import glob
import os
import re
import sys
from typing import Dict, List, Set, Tuple

from pydantic import BaseModel, Field

from llm7shi import Client

from common.canto_md import parse_oneline_md, parse_summary_md

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

PARTS = ["inferno", "purgatorio", "paradiso"]


class TrilingualOneline(BaseModel):
    """A whole canto's summary in one line, given in Italian and as strict translations of it"""
    summary_it: str = Field(
        description="One-sentence summary of the entire canto, in Italian, capturing its "
        "main events. No line breaks."
    )
    summary_en: str = Field(
        description="Strict English translation of summary_it: same content, same "
        "emphasis - not an independent summary. Under 40 words. No line breaks."
    )
    summary_ja: str = Field(
        description="Strict Japanese translation of summary_it: same content, same "
        "emphasis - not an independent summary. No line breaks."
    )


INSTRUCTIONS = """The messages above give this canto's segment summaries in Italian, English and Japanese (already a matched trilingual set, one line per segment).

Write a one-line summary of the whole canto in Italian, English and Japanese.

- Write exactly one sentence per language that captures the main events of the entire canto.
- Keep it concise (the English sentence under 40 words; keep Italian and Japanese proportionate).
- Write the Italian summary first, then make the English and Japanese summaries strict translations of it: the same content, in the same order, not independent summaries.
- Focus on the most important narrative events and characters, in the same style (tense, register) as the segment summaries above.
- Each of the three summaries must be a single sentence with no line breaks."""


def count_cantos(part: str) -> int:
    return len(glob.glob(os.path.join(SCRIPT_DIR, "..", "it", part, "[0-9][0-9].txt")))


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def build_messages(part: str, chapter: int, it_paras: List[str], en_paras: List[str], ja_paras: List[str]) -> List[str]:
    def fmt(paras: List[str]) -> str:
        return "\n".join(f"- {p}" for p in paras)

    return [
        f"[{part.title()} Canto {chapter} segment summaries, Italian]\n{fmt(it_paras)}",
        f"[{part.title()} Canto {chapter} segment summaries, English]\n{fmt(en_paras)}",
        f"[{part.title()} Canto {chapter} segment summaries, Japanese]\n{fmt(ja_paras)}",
        INSTRUCTIONS,
    ]


class OnelineWriter:
    """Rewrites a {part}-1.md file to a known-good set of cantos, then appends cantos one at a time."""

    def __init__(self, path: str, existing: Dict[int, str], keep: Set[int]):
        self.path = path
        with open(path, "w", encoding="utf-8") as f:
            for chapter in sorted(keep):
                f.write(f"{chapter}. {existing[chapter]}\n")

    def append(self, chapter: int, text: str) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"{chapter}. {text}\n")
            f.flush()


def parse_segment_arg(value: str) -> Tuple[str, int]:
    m = re.fullmatch(r"(\w+):(\d+)", value.strip())
    if not m:
        raise argparse.ArgumentTypeError("expected part:chapter, e.g. inferno:1")
    return m.group(1), int(m.group(2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate it/en/ja one-line canto summaries as a strict trilingual set"
    )
    parser.add_argument("-m", "--model", required=True,
                        help="LLM model to use (e.g. openai:gpt-5.6-terra)")
    parser.add_argument("-p", "--part", choices=PARTS, action="append",
                        help="Limit to this part (repeatable); default: all three, in order")
    parser.add_argument("--output-root", default="..",
                        help="Root directory containing it/, en/, ja/ (default: ..)")
    parser.add_argument("-s", "--segment", type=parse_segment_arg,
                        help="Debug: generate and print one part:chapter (e.g. inferno:1) "
                             "without touching any files")

    args = parser.parse_args()

    # Cantos are independent, so no turn is carried over into the next
    client = Client(model=args.model, show_params=args.segment is not None, keep_history=False)

    def load_part(part: str):
        it_cantos = parse_summary_md(os.path.join(args.output_root, "it", f"{part}.md"))
        en_cantos = parse_summary_md(os.path.join(args.output_root, "en", f"{part}.md"))
        ja_cantos = parse_summary_md(os.path.join(args.output_root, "ja", f"{part}.md"))
        return it_cantos, en_cantos, ja_cantos

    if args.segment:
        part, chapter = args.segment
        it_cantos, en_cantos, ja_cantos = load_part(part)
        it_paras, en_paras, ja_paras = it_cantos.get(chapter), en_cantos.get(chapter), ja_cantos.get(chapter)
        if not (it_paras and en_paras and ja_paras):
            print(f"Segment summaries not ready for {part}:{chapter}", file=sys.stderr)
            return 1
        messages = build_messages(part, chapter, it_paras, en_paras, ja_paras)
        resp = client(messages, schema=TrilingualOneline)
        print(f"\nit: {resp.data.summary_it}")
        print(f"en: {resp.data.summary_en}")
        print(f"ja: {resp.data.summary_ja}")
        return 0

    parts = args.part or PARTS
    total_processed = 0

    for part in parts:
        it_cantos, en_cantos, ja_cantos = load_part(part)
        total = count_cantos(part)

        it_path = os.path.join(args.output_root, "it", f"{part}-1.md")
        en_path = os.path.join(args.output_root, "en", f"{part}-1.md")
        ja_path = os.path.join(args.output_root, "ja", f"{part}-1.md")

        existing_it = parse_oneline_md(it_path)
        existing_en = parse_oneline_md(en_path)
        existing_ja = parse_oneline_md(ja_path)
        keep = existing_it.keys() & existing_en.keys() & existing_ja.keys()

        it_writer = OnelineWriter(it_path, existing_it, keep)
        en_writer = OnelineWriter(en_path, existing_en, keep)
        ja_writer = OnelineWriter(ja_path, existing_ja, keep)

        print(f"{part}: {len(keep)}/{total} cantos already done")

        for chapter in range(1, total + 1):
            if chapter in keep:
                continue

            it_paras, en_paras, ja_paras = it_cantos.get(chapter), en_cantos.get(chapter), ja_cantos.get(chapter)
            if not (it_paras and en_paras and ja_paras):
                print(f"{part} {chapter:2d} -> skipped (segment summaries not ready)")
                continue

            print(f"{part} {chapter:2d} -> ", end="", flush=True)
            messages = build_messages(part, chapter, it_paras, en_paras, ja_paras)
            resp = client(messages, schema=TrilingualOneline)

            it_text = normalize(resp.data.summary_it)
            en_text = normalize(resp.data.summary_en)
            ja_text = normalize(resp.data.summary_ja)

            it_writer.append(chapter, it_text)
            en_writer.append(chapter, en_text)
            ja_writer.append(chapter, ja_text)

            total_processed += 1
            print("done")

    print(f"\nProcessed {total_processed} cantos")

    return 0


if __name__ == "__main__":
    exit(main())
