"""Shared read/write helpers for the `{part}.md` per-canto summary files
(`it/{part}.md`, `en/{part}.md`, `ja/{part}.md`).

Format: a `## Canto N` heading, blank line, then one blank-line-separated
paragraph per segment, in segment order; no H1, no front matter. Consumed by
`templates/build.py` (site build) and `translate/summarize_segments.py`
(generation), and needed again by a future `summarize1.py` once it derives
per-canto one-liners from these segment paragraphs instead of from
`en.jsonl`/`ja.jsonl`.
"""

import re
from pathlib import Path
from typing import Dict, List, Union

CANTO_RE = re.compile(r"^## Canto (\d+)$", re.MULTILINE)


def split_cantos(text: str) -> Dict[int, str]:
    """Split a {part}.md file's text at each `## Canto N` heading."""
    chunks = CANTO_RE.split(text)[1:]
    return {int(chunks[i]): chunks[i + 1].strip("\n") for i in range(0, len(chunks), 2)}


def paragraphs(body: str) -> List[str]:
    """Split one canto's body into its per-segment paragraphs."""
    return [p.strip() for p in re.split(r"\n\s*\n", body.strip()) if p.strip()]


def parse_summary_md(path: Union[str, Path]) -> Dict[int, List[str]]:
    """chapter -> [segment 1 paragraph, segment 2 paragraph, ...] from a {part}.md file.

    Returns {} if the file doesn't exist.
    """
    path = Path(path)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    return {chapter: paragraphs(body) for chapter, body in split_cantos(text).items()}


def format_summary_md(chapters: Dict[int, List[str]]) -> str:
    """Render chapter -> [paragraph, ...] back into {part}.md text."""
    lines = []
    for i, chapter in enumerate(sorted(chapters)):
        if i:
            lines.append("")
        lines.append(f"## Canto {chapter}")
        for paragraph in chapters[chapter]:
            lines.append("")
            lines.append(paragraph)
    return "\n".join(lines) + "\n"
