"""Static site builder for dante-gemini-25.

Reads it/{part}/NN.txt, en/{part}/NN.txt, ja/{part}/NN.txt, it/{part}.md,
en/{part}.md, ja/{part}.md, it/{part}-1.md, en/{part}-1.md, ja/{part}-1.md
and generates:
- dist/{part}/NN.html    per-canto page with an Italian/English/Japanese
                         line-by-line trilingual layout
- dist/{part}/index.html per-canticle index page (Italian/English/Japanese
                         one-line summaries, side by side, per canto)
- dist/{part}/summary.html per-canticle summary page (Italian/English/Japanese
                         segment summaries, side by side, per canto)
- dist/index.html        landing page
- dist/assets/           static assets (reader.css)
- dist/images/           compressed illustrations (see images/compress.py)

Note: this reads only the expanded it/en/ja files, never en.jsonl/ja.jsonl -
translation fixes are made directly in the expanded files (see README.md).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from common.canto_md import parse_oneline_md, parse_summary_md

ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = TEMPLATES_DIR / "static"
DIST_DIR = ROOT / "dist"

PARTS = [
    {"key": "inferno", "label": "Inferno"},
    {"key": "purgatorio", "label": "Purgatorio"},
    {"key": "paradiso", "label": "Paradiso"},
]


@dataclass
class Canto:
    part: str
    number: int
    lines: list[tuple[int, str, str, str]] = field(default_factory=list)  # (lineno, it, en, ja)
    oneline_it: str = ""
    oneline_en: str = ""
    oneline_ja: str = ""
    is_last: bool = False


def count_cantos(part: str) -> int:
    return len(list((ROOT / "it" / part).glob("[0-9][0-9].txt")))


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").rstrip("\n").split("\n")


def load_canto_lines(part: str, number: int) -> list[tuple[int, str, str, str]]:
    it_path = ROOT / "it" / part / f"{number:02d}.txt"
    en_path = ROOT / "en" / part / f"{number:02d}.txt"
    ja_path = ROOT / "ja" / part / f"{number:02d}.txt"
    if not it_path.exists():
        raise SystemExit(
            f"Missing {it_path.relative_to(ROOT)}. "
            f"Run 'make -C it all split' to regenerate the Italian source text."
        )
    it_lines = read_lines(it_path)
    en_lines = read_lines(en_path)
    ja_lines = read_lines(ja_path)
    n = max(len(it_lines), len(en_lines), len(ja_lines))
    if len({len(it_lines), len(en_lines), len(ja_lines)}) != 1:
        print(
            f"Warning: line count mismatch in {part} {number:02d} "
            f"(it={len(it_lines)}, en={len(en_lines)}, ja={len(ja_lines)})"
        )
    it_lines += [""] * (n - len(it_lines))
    en_lines += [""] * (n - len(en_lines))
    ja_lines += [""] * (n - len(ja_lines))
    return list(zip(range(1, n + 1), it_lines, en_lines, ja_lines))


def load_segment_summaries(part: str) -> dict[int, list[tuple[str, str, str]]]:
    """Return canto -> [(it_paragraph, en_paragraph, ja_paragraph), ...]."""
    it_cantos = parse_summary_md(ROOT / "it" / f"{part}.md")
    en_cantos = parse_summary_md(ROOT / "en" / f"{part}.md")
    ja_cantos = parse_summary_md(ROOT / "ja" / f"{part}.md")

    total = count_cantos(part)
    expected = set(range(1, total + 1))
    for lang, cantos in (("it", it_cantos), ("en", en_cantos), ("ja", ja_cantos)):
        missing = sorted(expected - cantos.keys())
        if missing:
            raise SystemExit(
                f"{lang}/{part}.md is missing canto(s) {missing} (expected 1..{total}). "
                f"Run 'make -C translate summarize' to finish generating it."
            )

    result = {}
    for number in sorted(expected):
        it_paras, en_paras, ja_paras = it_cantos[number], en_cantos[number], ja_cantos[number]
        if len({len(it_paras), len(en_paras), len(ja_paras)}) != 1:
            print(
                f"Warning: summary paragraph count mismatch in {part} canto {number} "
                f"(it={len(it_paras)}, en={len(en_paras)}, ja={len(ja_paras)})"
            )
        result[number] = list(zip(it_paras, en_paras, ja_paras))
    return result


def load_oneline(part: str) -> dict[int, dict[str, str]]:
    """Return canto -> {"it": text, "en": text, "ja": text} from {part}-1.md."""
    result: dict[int, dict[str, str]] = {}
    for lang in ("it", "en", "ja"):
        for number, text in parse_oneline_md(ROOT / lang / f"{part}-1.md").items():
            result.setdefault(number, {})[lang] = text
    return result


def canto_href(part: str, number: int) -> str:
    return f"{part}/{number:02d}.html"


def part_href(part: str) -> str:
    return f"{part}/index.html"


def summary_href(part: str) -> str:
    return f"{part}/summary.html"


def load_part_cantos(part: str) -> list[Canto]:
    total = count_cantos(part)
    onelines = load_oneline(part)
    cantos = []
    for number in range(1, total + 1):
        canto = Canto(
            part=part,
            number=number,
            lines=load_canto_lines(part, number),
            oneline_it=onelines.get(number, {}).get("it", ""),
            oneline_en=onelines.get(number, {}).get("en", ""),
            oneline_ja=onelines.get(number, {}).get("ja", ""),
            is_last=(number == total),
        )
        cantos.append(canto)
    return cantos


def build_sidebar_parts(all_cantos: dict[str, list[Canto]]) -> list[dict]:
    sidebar_parts = []
    for part_cfg in PARTS:
        key = part_cfg["key"]
        cantos = all_cantos[key]
        sidebar_parts.append({
            "key": key,
            "label": part_cfg["label"],
            "href": part_href(key),
            "summary_href": summary_href(key),
            "cantos": [
                {
                    "number": c.number,
                    "href": canto_href(key, c.number),
                    "title": c.oneline_en,
                }
                for c in cantos
            ],
        })
    return sidebar_parts


def build_canto_pages(env: Environment, all_cantos: dict[str, list[Canto]], sidebar_parts: list[dict]) -> None:
    template = env.get_template("canto.html")
    count = 0
    for part_index, part_cfg in enumerate(PARTS):
        key = part_cfg["key"]
        cantos = all_cantos[key]
        for i, canto in enumerate(cantos):
            if i > 0:
                prev_href = canto_href(key, canto.number - 1)
                prev_label = f"Canto {canto.number - 1}"
            elif part_index > 0:
                prev_part = PARTS[part_index - 1]
                prev_total = len(all_cantos[prev_part["key"]])
                prev_href = canto_href(prev_part["key"], prev_total)
                prev_label = f"{prev_part['label']} — Canto {prev_total}"
            else:
                prev_href = None
                prev_label = None

            if i < len(cantos) - 1:
                next_href = canto_href(key, canto.number + 1)
                next_label = f"Canto {canto.number + 1}"
            elif part_index < len(PARTS) - 1:
                next_part = PARTS[part_index + 1]
                next_href = canto_href(next_part["key"], 1)
                next_label = f"{next_part['label']} — Canto 1"
            else:
                next_href = None
                next_label = None

            html_out = template.render(
                part_key=key,
                part_label=part_cfg["label"],
                canto=canto,
                prev_href=prev_href,
                prev_label=prev_label,
                next_href=next_href,
                next_label=next_label,
                part_href=part_href(key),
                base="../",
                sidebar_parts=sidebar_parts,
                current_part=key,
                current_canto=canto.number,
            )
            out = DIST_DIR / canto_href(key, canto.number)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(html_out, encoding="utf-8")
            count += 1
    print(f"  wrote {count} canto pages")


def build_part_index_pages(env: Environment, all_cantos: dict[str, list[Canto]], sidebar_parts: list[dict]) -> None:
    template = env.get_template("part_index.html")
    for part_cfg in PARTS:
        key = part_cfg["key"]
        cantos = [
            {
                "number": c.number,
                "href": canto_href(key, c.number),
                "oneline_it": c.oneline_it,
                "oneline_en": c.oneline_en,
                "oneline_ja": c.oneline_ja,
            }
            for c in all_cantos[key]
        ]
        html_out = template.render(
            part_key=key,
            part_label=part_cfg["label"],
            cantos=cantos,
            base="../",
            sidebar_parts=sidebar_parts,
            current_part=key,
            current_view="index",
        )
        out = DIST_DIR / part_href(key)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_out, encoding="utf-8")
    print(f"  wrote {len(PARTS)} canticle index pages")


def build_summary_pages(env: Environment, sidebar_parts: list[dict]) -> None:
    template = env.get_template("summary.html")
    for part_cfg in PARTS:
        key = part_cfg["key"]
        summaries = load_segment_summaries(key)
        cantos = [
            {
                "number": number,
                "href": canto_href(key, number),
                "paragraphs": paras,
            }
            for number, paras in sorted(summaries.items())
        ]
        html_out = template.render(
            part_key=key,
            part_label=part_cfg["label"],
            cantos=cantos,
            base="../",
            sidebar_parts=sidebar_parts,
            current_part=key,
            current_view="summary",
        )
        out = DIST_DIR / summary_href(key)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_out, encoding="utf-8")
    print(f"  wrote {len(PARTS)} summary pages")


def build_index(env: Environment, sidebar_parts: list[dict]) -> None:
    template = env.get_template("index.html")
    html_out = template.render(
        base="",
        sidebar_parts=sidebar_parts,
        parts=PARTS,
    )
    out = DIST_DIR / "index.html"
    out.write_text(html_out, encoding="utf-8")
    print(f"  wrote {out.relative_to(ROOT)}")


def copy_static() -> None:
    assets = DIST_DIR / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(STATIC_DIR, assets)
    print(f"  copied static -> {assets.relative_to(ROOT)}")


def main() -> None:
    DIST_DIR.mkdir(exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )

    print("Loading cantos...")
    all_cantos = {part_cfg["key"]: load_part_cantos(part_cfg["key"]) for part_cfg in PARTS}
    sidebar_parts = build_sidebar_parts(all_cantos)

    print("Building canto pages...")
    build_canto_pages(env, all_cantos, sidebar_parts)

    print("Building canticle index pages...")
    build_part_index_pages(env, all_cantos, sidebar_parts)

    print("Building summary pages...")
    build_summary_pages(env, sidebar_parts)

    print("Building index...")
    build_index(env, sidebar_parts)

    print("Copying static assets...")
    copy_static()

    print("Done. Run 'make images' to compress illustrations into dist/images/.")


if __name__ == "__main__":
    main()
