"""Regenerate the per-segment summaries in it/en/ja as a strict trilingual set.

`../en/{part}.md` and `../ja/{part}.md` were originally expanded by
`convert.py` from `../en.jsonl` / `../ja.jsonl`, whose `summary` fields come
from two independent translation jobs - so the English and Japanese
paragraphs `templates/build.py` zips together for the summary pages do not
actually correspond to each other, and there is no Italian summary at all.

This script regenerates all three from scratch, segment by segment, using
the Italian source as the anchor: for each segment it asks the model to
write an Italian summary and strict English/Japanese translations of it,
using the existing (mismatched) en.jsonl/ja.jsonl summaries only as a
starting point for scope and detail, and the immediately preceding
segment's regenerated summaries as continuity context. Results are appended
to `../it/{part}.md`, `../en/{part}.md`, `../ja/{part}.md` as they are
produced. If interrupted, re-running loads those files and skips the
segments already done.

Output format matches `convert.py` exactly, since `templates/build.py`
parses it: a `## Canto N` heading followed by one blank-line-separated,
single-line paragraph per segment.
"""

import argparse
import glob
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from llm7shi import Client

from common.canto_md import format_summary_md, parse_summary_md

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

PARTS = ["inferno", "purgatorio", "paradiso"]


class TrilingualSummary(BaseModel):
    """A single segment's summary, given in Italian and as strict translations of it"""
    summary_it: str = Field(
        description="Summary of this segment's content, in Italian, grounded in the "
        "Italian source text above. No line breaks."
    )
    summary_en: str = Field(
        description="Strict English translation of summary_it: same sentences, same "
        "order, same information - not an independent summary. No line breaks."
    )
    summary_ja: str = Field(
        description="Strict Japanese translation of summary_it: same sentences, same "
        "order, same information - not an independent summary. No line breaks."
    )


INSTRUCTIONS = """The messages above give, for one segment of Dante's Divine Comedy:
- the Italian source text of the segment
- the existing English and Japanese summaries of it (generated independently of each other, so they do not necessarily agree)
- the regenerated summaries of the immediately preceding segment, for continuity

Write a new summary of this segment in Italian, English and Japanese.

- Ground the summary in the Italian source text. Use the existing English/Japanese summaries only as a guide to the expected scope and level of detail - where they disagree with the source or each other, follow the source.
- Write the Italian summary first, then make the English and Japanese summaries strict translations of it: the same sentences, in the same order, conveying the same information. Do not let them diverge into independent summaries.
- Match the existing summaries' overall length and level of detail.
- Do not mention the canto or segment number, and do not use meta-phrases like "this segment" or "in this passage" - summarize the content directly, as the existing summaries do.
- Each of the three summaries must be a single block of text with no line breaks."""


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_source_chapters() -> Dict[str, List[List[str]]]:
    """part -> [chapter 1 segments, chapter 2 segments, ...], each segment one joined string."""
    chapters = {}
    for part in PARTS:
        segmentation_file = os.path.join(SCRIPT_DIR, f"{part}.jsonl")
        directory = os.path.join(SCRIPT_DIR, "..", "it", part)

        segmentation_data = {}
        with open(segmentation_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    segmentation_data[data["chapter"]] = data

        chapter_files = sorted(glob.glob(os.path.join(directory, "*.txt")))
        if not chapter_files:
            raise FileNotFoundError(f"No .txt files found in directory '{directory}'")

        blocks = []
        for chapter_file in chapter_files:
            chapter_num = int(os.path.basename(chapter_file).replace(".txt", ""))
            with open(chapter_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]

            if chapter_num in segmentation_data:
                segments = []
                for boundary in segmentation_data[chapter_num]["boundaries"]:
                    start_line = boundary["start_line"] - 1
                    end_line = boundary["end_line"] - 1
                    if start_line < len(lines) and end_line < len(lines):
                        segments.append("\n".join(lines[start_line:end_line + 1]))
                blocks.append(segments)
            else:
                blocks.append(["\n".join(lines)])

        chapters[part] = blocks
    return chapters


def ordered_keys(chapters: Dict[str, List[List[str]]], part: str) -> List[Tuple[int, int, int]]:
    """[(chapter, segment, total_segments_in_chapter), ...] in generation order."""
    keys = []
    for chapter_num, segments in enumerate(chapters[part], 1):
        total = len(segments)
        for segment_num in range(1, total + 1):
            keys.append((chapter_num, segment_num, total))
    return keys


def load_existing_summaries(jsonl_path: str) -> Dict[Tuple[str, int, int], str]:
    """(part, chapter, segment) -> summary, from en.jsonl or ja.jsonl."""
    result = {}
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            key = (record["part"], record["chapter"], record["segment"])
            result[key] = record["response"]["summary"]
    return result


def flatten(by_chapter: Dict[int, List[str]], keys: List[Tuple[int, int, int]]) -> List[Optional[str]]:
    """Align a chapter->paragraphs map onto the full ordered key list."""
    out = []
    for chapter_num, segment_num, _ in keys:
        paragraphs = by_chapter.get(chapter_num, [])
        out.append(paragraphs[segment_num - 1] if segment_num <= len(paragraphs) else None)
    return out


def common_prefix_len(*lists: List[Optional[str]]) -> int:
    n = 0
    for values in zip(*lists):
        if any(v is None for v in values):
            break
        n += 1
    return n


class SummaryWriter:
    """Rewrites a {part}.md file to a known-good prefix, then appends segments one at a time."""

    def __init__(self, path: str, keys: List[Tuple[int, int, int]], texts: List[Optional[str]], prefix_len: int):
        self.path = path
        self.keys = keys

        chapters: Dict[int, List[str]] = {}
        for i in range(prefix_len):
            chapter_num, _, _ = keys[i]
            chapters.setdefault(chapter_num, []).append(texts[i])
        with open(path, "w", encoding="utf-8") as f:
            f.write(format_summary_md(chapters))

        self.last_chapter: Optional[int] = keys[prefix_len - 1][0] if prefix_len else None
        self.first_write = prefix_len == 0

    def append(self, index: int, text: str) -> None:
        chapter_num, _, _ = self.keys[index]
        with open(self.path, "a", encoding="utf-8") as f:
            if chapter_num != self.last_chapter:
                if not self.first_write:
                    f.write("\n")
                f.write(f"## Canto {chapter_num}\n")
                self.last_chapter = chapter_num
                self.first_write = False
            if not self.first_write:
                f.write("\n")
            f.write(text + "\n")
            self.first_write = False
            f.flush()


def parse_segment_arg(value: str) -> Tuple[str, int, int]:
    m = re.fullmatch(r"(\w+):(\d+):(\d+)", value.strip())
    if not m:
        raise argparse.ArgumentTypeError(
            "expected part:chapter:segment, e.g. inferno:11:3"
        )
    return m.group(1), int(m.group(2)), int(m.group(3))


def build_messages(
    source_lines: str,
    existing_en: str,
    existing_ja: str,
    prev: Optional[Tuple[str, str, str]],
    part: str,
    chapter_num: int,
    segment_num: int,
    total_segments: int,
) -> List[str]:
    messages = [
        f"[Italian source text: {part.title()}, Canto {chapter_num}, segment {segment_num}/{total_segments}]\n{source_lines}",
        f"[Existing English summary]\n{existing_en}",
        f"[Existing Japanese summary]\n{existing_ja}",
    ]
    if prev is not None:
        prev_it, prev_en, prev_ja = prev
        messages.append(
            "[Regenerated summaries of the immediately preceding segment, for continuity]\n"
            f"Italian: {prev_it}\nEnglish: {prev_en}\nJapanese: {prev_ja}"
        )
    messages.append(INSTRUCTIONS)
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate it/en/ja segment summaries as a strict trilingual set"
    )
    parser.add_argument("-m", "--model", required=True,
                        help="LLM model to use (e.g. openai:gpt-5.6-terra)")
    parser.add_argument("-p", "--part", choices=PARTS, action="append",
                        help="Limit to this part (repeatable); default: all three, in order")
    parser.add_argument("--output-root", default="..",
                        help="Root directory containing it/, en/, ja/ (default: ..)")
    parser.add_argument("-s", "--segment", type=parse_segment_arg,
                        help="Debug: generate and print one part:chapter:segment (e.g. "
                             "inferno:1:1) without touching any files")

    args = parser.parse_args()

    chapters = load_source_chapters()
    en_summaries = load_existing_summaries(os.path.join(args.output_root, "en.jsonl"))
    ja_summaries = load_existing_summaries(os.path.join(args.output_root, "ja.jsonl"))

    client = Client(model=args.model, show_params=args.segment is not None)

    def get_source(part: str, chapter_num: int, segment_num: int) -> str:
        return chapters[part][chapter_num - 1][segment_num - 1]

    if args.segment:
        part, chapter_num, segment_num = args.segment
        keys = ordered_keys(chapters, part)
        if (chapter_num, segment_num) not in [(c, s) for c, s, _ in keys]:
            print(f"No such segment: {part}:{chapter_num}:{segment_num}", file=sys.stderr)
            return 1
        total_segments = len(chapters[part][chapter_num - 1])
        messages = build_messages(
            get_source(part, chapter_num, segment_num),
            en_summaries.get((part, chapter_num, segment_num), ""),
            ja_summaries.get((part, chapter_num, segment_num), ""),
            None, part, chapter_num, segment_num, total_segments,
        )
        # See the comment above the loop in main() for why this is client.copy()
        # rather than client() directly.
        c = client.copy()
        resp = c(messages, schema=TrilingualSummary)
        print(f"\nit: {resp.data.summary_it}")
        print(f"en: {resp.data.summary_en}")
        print(f"ja: {resp.data.summary_ja}")
        return 0

    parts = args.part or PARTS
    total_processed = 0
    total_violations = 0

    for part in parts:
        keys = ordered_keys(chapters, part)

        it_path = os.path.join(args.output_root, "it", f"{part}.md")
        en_path = os.path.join(args.output_root, "en", f"{part}.md")
        ja_path = os.path.join(args.output_root, "ja", f"{part}.md")

        it_texts = flatten(parse_summary_md(it_path), keys)
        en_texts = flatten(parse_summary_md(en_path), keys)
        ja_texts = flatten(parse_summary_md(ja_path), keys)

        prefix_len = common_prefix_len(it_texts, en_texts, ja_texts)

        it_writer = SummaryWriter(it_path, keys, it_texts, prefix_len)
        en_writer = SummaryWriter(en_path, keys, en_texts, prefix_len)
        ja_writer = SummaryWriter(ja_path, keys, ja_texts, prefix_len)

        prev = None
        if prefix_len:
            prev = (it_texts[prefix_len - 1], en_texts[prefix_len - 1], ja_texts[prefix_len - 1])

        print(f"{part}: {prefix_len}/{len(keys)} segments already done")

        # Client.__call__ appends every prompt/response to self.history and
        # resends it on every subsequent call, so calling the shared `client`
        # directly in this loop would make each segment's request carry the
        # full transcript of every segment before it - a cost that grows
        # quadratically over a 376-segment run (this is what previously
        # blew up token usage to millions of tokens and hit the API rate
        # limit). Segments are independent and get their continuity from the
        # explicit `prev` argument, not from conversation history, so each
        # iteration must call a fresh client.copy() with empty history.
        for i in range(prefix_len, len(keys)):
            chapter_num, segment_num, total_segments = keys[i]
            print(f"{part} {chapter_num:2d}:{segment_num} -> ", end="", flush=True)

            messages = build_messages(
                get_source(part, chapter_num, segment_num),
                en_summaries.get((part, chapter_num, segment_num), ""),
                ja_summaries.get((part, chapter_num, segment_num), ""),
                prev, part, chapter_num, segment_num, total_segments,
            )
            c = client.copy()
            resp = c(messages, schema=TrilingualSummary)

            it_text = normalize(resp.data.summary_it)
            en_text = normalize(resp.data.summary_en)
            ja_text = normalize(resp.data.summary_ja)
            if (it_text != resp.data.summary_it.strip()
                    or en_text != resp.data.summary_en.strip()
                    or ja_text != resp.data.summary_ja.strip()):
                total_violations += 1
                print("(line break removed) ", end="")

            it_writer.append(i, it_text)
            en_writer.append(i, en_text)
            ja_writer.append(i, ja_text)

            prev = (it_text, en_text, ja_text)
            total_processed += 1
            print("done")

    print(f"\nProcessed {total_processed} segments")
    print(f"Line-break violations fixed: {total_violations}")

    return 0


if __name__ == "__main__":
    exit(main())
