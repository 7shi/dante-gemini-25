"""Re-flow an existing segment translation onto the source's line count.

translate_segments.py already asks for one output line per source line, but a
handful of segments still come back with the wrong line count - anything from
a couple of lines off to the whole segment collapsed into one line of prose.
This script does not re-translate: it takes the translation that is already
there and asks the model to redistribute it over the source's lines, moving a
word or two at a seam only where the split makes it necessary. The record is
rewritten in place in the given JSONL file (en.jsonl or ja.jsonl).
"""

import argparse
import difflib
import json
import os
import re
import sys
from typing import Dict, List, Tuple

from llm7shi import Client

from translate_segments import load_chapter_blocks_from_directory

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

PARTS = ["inferno", "purgatorio", "paradiso"]

INSTRUCTIONS = """The text above is an existing translation of the numbered source lines. Its line count does not match the source's, so the line structure needs to be restored.

Your task is to redistribute the existing translation over the source's lines and prefix every line with its source line number, numbered consecutively from 1, one output line per source line, in order.

This is not a translation task and not a proofreading task. Reproduce the existing translation word for word. Where its wording does not divide cleanly at a source line's boundary, adjust it at that boundary only: move the fewest words needed, and add or drop only what the split itself makes necessary.

Constraints:
- Every output line must be written in {target_lang}.
- Change nothing else. Leave wording, punctuation, spelling and names exactly as they are - including anything you judge to be a mistranslation, an error or an awkward phrase. Correcting it is out of scope here.
- The line structure takes priority over prose flow. Never merge, split or drop a source line to make the result read better.
- Output the numbered lines only. No commentary, no headings, no blank lines."""

LINE_RE = re.compile(r"^\s*(\d+)[.:)]?\s+(.*)$")

QUOTES = str.maketrans({c: "'" for c in "‘’“”\""})


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).translate(QUOTES)


def number_lines(lines: List[str]) -> str:
    return "\n".join(f"{i} {line}" for i, line in enumerate(lines, 1))


def parse_numbered(text: str) -> Tuple[List[int], List[str]]:
    numbers, texts = [], []
    for line in text.strip().split("\n"):
        if not line.strip():
            continue
        if m := LINE_RE.match(line):
            numbers.append(int(m.group(1)))
            texts.append(m.group(2).strip())
        else:
            numbers.append(0)
            texts.append(line.strip())
    return numbers, texts


def align_segment(
    client: Client,
    source_lines: List[str],
    translation: str,
    source_lang: str,
    target_lang: str,
) -> str:
    c = client.copy()
    messages = [
        f"[Source text in {source_lang}, one numbered line per line]\n{number_lines(source_lines)}",
        f"[Existing {target_lang} translation of the text above]\n{translation}",
        INSTRUCTIONS.format(target_lang=target_lang),
    ]
    return c(messages).text.strip()


DRIFT_LIMIT = 0.05


def check(source_lines: List[str], translation: str, response: str) -> Tuple[List[str], float]:
    numbers, texts = parse_numbered(response)
    problems = []

    expected = list(range(1, len(source_lines) + 1))
    if numbers != expected:
        if len(numbers) != len(expected):
            problems.append(f"line count {len(numbers)} != {len(expected)}")
        else:
            problems.append("line numbering not consecutive from 1")

    before, after = normalize(translation), normalize("\n".join(texts))
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    drift = 0.0 if before == after else 1.0 - matcher.ratio()
    if drift > DRIFT_LIMIT:
        problems.append(f"drift over {DRIFT_LIMIT * 100:.1f}%")

    return problems, drift


def load_records(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_records(path: str, records: List[Dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_source_chapters() -> Dict[str, List[List[str]]]:
    chapters = {}
    for part in PARTS:
        data = load_chapter_blocks_from_directory(
            os.path.join(SCRIPT_DIR, f"{part}.jsonl"),
            os.path.join(SCRIPT_DIR, part),
        )
        chapters[part] = data["chapters"]
    return chapters


def get_source_lines(chapters: Dict[str, List[List[str]]], part: str, chapter: int, segment: int) -> List[str]:
    blocks = chapters[part]
    if chapter > len(blocks) or segment > len(blocks[chapter - 1]):
        return None
    return blocks[chapter - 1][segment - 1].split("\n")


def parse_segment_arg(value: str) -> List[Tuple[str, int, int]]:
    segments = []
    for item in value.split(","):
        m = re.fullmatch(r"(\w+):(\d+):(\d+)", item.strip())
        if not m:
            raise argparse.ArgumentTypeError(
                "expected part:chapter:segment or a comma-separated list, "
                "e.g. inferno:11:3 or purgatorio:18:1,purgatorio:18:2"
            )
        segments.append((m.group(1), int(m.group(2)), int(m.group(3))))
    return segments


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-flow existing translations onto the source's line count"
    )
    parser.add_argument("jsonl_file", help="Translation JSONL to fix in place (e.g. en.jsonl)")
    parser.add_argument("-m", "--model", required=True,
                        help="LLM model to use (e.g. openai:gpt-5.6-terra)")
    parser.add_argument("-s", "--segment", type=parse_segment_arg,
                        help="Process only these part:chapter:segment references, comma separated "
                             "(e.g. inferno:11:3 or purgatorio:18:1,purgatorio:18:2). "
                             "Without it, every segment whose line count does not match the "
                             "source is processed")

    args = parser.parse_args()

    chapters = load_source_chapters()
    records = load_records(args.jsonl_file)
    index = {(r["part"], r["chapter"], r["segment"]): i for i, r in enumerate(records)}

    if args.segment:
        wanted = args.segment
        if missing := [s for s in wanted if s not in index]:
            for part, chapter, segment in missing:
                print(f"No such segment: {part}:{chapter}:{segment}", file=sys.stderr)
            return 1
        targets = wanted
    else:
        targets = []
        for key, i in index.items():
            part, chapter, segment = key
            source_lines = get_source_lines(chapters, part, chapter, segment)
            if source_lines is None:
                continue
            translation = records[i]["response"]["translation"]
            if len(translation.split("\n")) != len(source_lines):
                targets.append(key)
        targets.sort(key=lambda k: (PARTS.index(k[0]) if k[0] in PARTS else 99, k[1], k[2]))

    client = Client(model=args.model, show_params=len(targets) == 1)

    violations: List[Tuple[str, int, int, List[str], float]] = []
    processed = 0

    for part, chapter, segment in targets:
        record = records[index[(part, chapter, segment)]]
        source_lines = get_source_lines(chapters, part, chapter, segment)
        if source_lines is None:
            print(f"{part} {chapter:2d}:{segment} -> no source segment", file=sys.stderr)
            continue

        translation = record["response"]["translation"]
        print(f"\n{part} {chapter:2d}:{segment} -> aligning "
              f"({len(translation.split(chr(10)))} lines -> {len(source_lines)} source lines)")

        response = align_segment(
            client, source_lines, translation,
            record["source_lang"], record["target_lang"],
        )

        problems, drift = check(source_lines, translation, response)
        if problems:
            violations.append((part, chapter, segment, problems, drift))
            print(f"  violation: {', '.join(problems)}")
        print(f"  drift: {drift * 100:.1f}%")

        _, texts = parse_numbered(response)
        record["response"]["translation"] = "\n".join(texts)
        save_records(args.jsonl_file, records)
        processed += 1

    print(f"\nProcessed {processed} segments -> {args.jsonl_file}")
    print(f"Violations: {len(violations)}/{processed}")
    for part, chapter, segment, problems, drift in violations:
        print(f"  {part} {chapter:2d}:{segment} {', '.join(problems)} (drift {drift * 100:.1f}%)")

    return 0


if __name__ == "__main__":
    exit(main())
