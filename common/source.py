"""The Italian source text and its segmentation, read from dante-corpus.

This repository used to keep its own copy of the poem in `it/{part}/NN.txt`,
split out of the Gutenberg text by `it/Makefile`. That copy writes elisions
with ’ (`ch’i’`) - the same character that closes a ‘ ’ quotation - so a
quotation mark cannot be told from an apostrophe there. dante-corpus
normalizes elisions to ASCII `'` and leaves « » “ ” ‘ ’ to speech alone,
which is what anything reasoning about who is speaking needs. The text is
otherwise identical, line for line, in all 100 cantos.

`segments/{part}.jsonl` still supplies the segment boundaries, so a caller
that wants a canticle split into translation-sized blocks asks for
`chapter_blocks()` and gets the same structure the directory-based loader
used to return.
"""

import json
import os
from typing import Dict, List

from dante_corpus import cantos, ref

PARTS = ["inferno", "purgatorio", "paradiso"]


def count_cantos(part: str) -> int:
    return len(cantos(part))


def canto_lines(part: str, number: int) -> List[str]:
    return [line.text for line in ref(f"{part} {number}")]


def load_segmentation(segmentation_file: str) -> Dict[int, Dict]:
    """chapter -> its segmentation record, or {} if the file does not exist."""
    if not os.path.exists(segmentation_file):
        return {}
    with open(segmentation_file, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    return {record["chapter"]: record for record in records}


def chapter_blocks(segmentation_file: str, part: str) -> Dict:
    """{"title": part, "chapters": [[segment text, ...], ...]} for one canticle.

    Chapters come in canto order and each segment is one string of joined
    lines. A chapter the segmentation file does not cover becomes a single
    segment holding the whole canto.
    """
    segmentation = load_segmentation(segmentation_file)

    blocks = []
    for number in cantos(part):
        lines = canto_lines(part, number)
        if number in segmentation:
            segments = []
            for boundary in segmentation[number]["boundaries"]:
                start = boundary["start_line"] - 1
                end = boundary["end_line"] - 1
                if start < len(lines) and end < len(lines):
                    segments.append("\n".join(lines[start:end + 1]))
            blocks.append(segments)
        else:
            blocks.append(["\n".join(lines)])

    return {"title": part.title(), "chapters": blocks}
