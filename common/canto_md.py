"""Shared read/write helpers for the per-canto summary markdown files:
`{part}.md` (`it/`, `en/`, `ja/` - one paragraph per segment) and
`{part}-1.md` (one line per canto). Consumed by `templates/build.py` (site
build) and `translate/summarize_segments.py` / `translate/summarize1.py`
(generation).
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
    """Render chapter -> [paragraph, ...] back into {part}.md text.

    Empty input renders as "", not "\\n": summarize_segments.py writes this
    out before appending its first segment, and a lone newline there would
    leave the file starting with a blank line.
    """
    lines = []
    for i, chapter in enumerate(sorted(chapters)):
        if i:
            lines.append("")
        lines.append(f"## Canto {chapter}")
        for paragraph in chapters[chapter]:
            lines.append("")
            lines.append(paragraph)
    return "\n".join(lines) + "\n" if lines else ""


ONELINE_RE = re.compile(r"^(\d+)\.\s+(.*)$")


def parse_oneline_md(path: Union[str, Path]) -> Dict[int, str]:
    """chapter -> one-line summary, from a {part}-1.md file. Returns {} if the file doesn't exist."""
    path = Path(path)
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ONELINE_RE.match(line.strip())
        if m:
            result[int(m.group(1))] = m.group(2)
    return result
