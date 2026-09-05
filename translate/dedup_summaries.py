"""Remove cross-segment repetition from a canto's segment summaries.

For a canto you have looked at and judged repetitive - `-c inferno:28` -
not for a pass over everything. Running it over all 100 cantos was
considered and dropped: sampling the cantos that a repeated-phrase scan
ranked highest turned up almost nothing worth changing. Where a later
segment does echo an earlier one, it is usually either a deliberate echo in
the poem (Mosca asking to be remembered after Pier da Medicina - the same
words, a different speaker, so not a repetition at all), a connective back-
reference that reads naturally because `summarize_segments.py` had the
preceding segment in front of it, or a re-introduction after enough
intervening material that the reader is glad of it. The cost of a full run
buys no improvement over that. What is left for this script is the
occasional case where none of those apply and the repetition grates.

`summarize_segments.py` writes `../it/{part}.md` one segment at a time, with
only the immediately preceding segment as context, so a later segment often
restates what an earlier one already established - that Dante is alive, how
the bolgia's punishment works, that a damned soul asks to be remembered.
Nothing in that pipeline can see a canto as a whole, and the repetition is
semantic rather than literal, so it does not show up in any mechanical check.
The paragraphs are published one after another and read straight through, so
what is being fixed here is how the canto reads in sequence - which is also
the standard the model is given, rather than a rule about repeated facts.

This script takes one canto at a time, as a three-turn conversation:

1. It hands the model all of that canto's current Italian summaries and asks
   it to keep the first occurrence of each piece of information and trim the
   restatements. The Italian source text is deliberately not shown - with it
   in the prompt the model can see that a restatement is grounded in the
   poem and defends it instead of removing it, which is the wrong question
   here: the summaries, not the source, are what is being edited.
2. It then hands the model the existing English summaries of the same canto,
   and after them the Japanese ones, asking each time for the same edits to
   be carried across. The corrected Italian is already in the conversation,
   so it costs nothing to resend, and the three files stay a matched set.

Each canto gets its own `Client`, so no canto's turns can leak into the
next one's context.

Results are written as they are produced, and the changed segments printed
as `-`/`+` pairs. Writing is the default because the edit cannot be known
without generating it: withholding the result by default would only mean
paying for a generation and discarding it, then paying again for the real
run. Review with `git diff` and undo with `git checkout` - which is why the
summary files should be committed before a run. `--no-write` prints without
writing, for trying out a prompt change against the summaries on disk
without having to restore them afterwards.
"""

import argparse
import re
import sys
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field

from llm7shi import Client

from common.canto_md import format_summary_md, parse_summary_md
from summarize_segments import PARTS, normalize

MAX_ATTEMPTS = 3


class DedupedSummaries(BaseModel):
    """A canto's segment summaries with cross-segment repetition removed"""
    segments: List[str] = Field(
        description="The canto's summaries in Italian, one per segment, in the same "
        "order and the same number as the summaries given above. Each is a single "
        "block of text with no line breaks."
    )


class AlignedEnglish(BaseModel):
    """The English counterparts of the corrected Italian summaries"""
    segments: List[str] = Field(
        description="The canto's summaries in English, one per segment, in the same "
        "order and the same number as the summaries given above. Each is a single "
        "block of text with no line breaks."
    )


class AlignedJapanese(BaseModel):
    """The Japanese counterparts of the corrected Italian summaries"""
    segments: List[str] = Field(
        description="The canto's summaries in Japanese, one per segment, in the same "
        "order and the same number as the summaries given above. Each is a single "
        "block of text with no line breaks."
    )


INSTRUCTIONS_IT = """The message above gives the summaries of one canto of Dante's Divine Comedy, one per segment of the canto, numbered and in order.

They are published together, one paragraph after another, and read straight through as a single account of the canto. But they were written one segment at a time, without sight of one another, so a later one often restates what an earlier one already established, as if the reader were meeting it for the first time.

Rewrite them so that they read naturally in sequence: each piece of information given once, where it first arises, and everything after it written for a reader who has just read that. Reading the whole canto through is the test - a paragraph that reads well on its own but repeats the one before it is wrong.

- Keep the first occurrence. Where a later summary restates something an earlier one already established - that Dante is alive, how the bolgia's punishment works, where the poets are - remove the restatement from the later summary. That the restated fact is true, and stated in the poem, is not a reason to keep it: it is already in the canto's summaries, and that is what makes it a repetition.
- One kind of repetition stays: when a character does again what an earlier one did (Mosca asking to be remembered after Pier da Medicina has asked the same). That is a second event, not a restatement, and dropping it would lose what Mosca said. Keep it, but write it as the echo it is - «anche», «a sua volta» - which is also how it reads naturally after the first.
- Do not resummarize the canto as a whole and redistribute it. Each summary stays with the events it already covers, in the same order.
- Change nothing else. The wording, length and level of detail of everything that is not a repetition must stay exactly as it is, and a segment with nothing to remove must be returned verbatim.
- A pronoun left dangling by a removal is never a reason to keep the repetition: remove it anyway, then repair the pronoun. Within a segment the name must come before the pronouns referring to it, and a mention of the name further on does not license an earlier pronoun, so where a removal leaves one stranded, write the name in its place. «Pier da Medicina riconosce Dante come vivo e gli chiede di ricordarsi di lui» becomes «Pier da Medicina chiede a Dante di ricordarsi di lui» - the restatement gone and the pronoun resolved, in one step.
- Return exactly one summary per segment, in the original order. Do not merge, split or reorder them.
- Write in Italian. Each summary is a single block of text with no line breaks."""


def translation_instructions(language: str) -> str:
    return f"""The message above gives the existing {language} summaries of the same canto, one per segment, in the same order. They were translated from the Italian summaries as they stood before your corrections.

Bring them into line with the corrected Italian summaries you have just written.

- Make the same changes you made to the Italian, and only those: the same removals, and the same repairs to what a removal left behind.
- Keep the existing {language} wording wherever the Italian was left unchanged. A summary whose Italian you did not change must be returned verbatim.
- Where the Italian did change, the {language} must say what the corrected Italian says - the same sentences, in the same order, with the same information - rather than a fresh rendering of the passage.
- Pronouns do not carry over. A removal that left the Italian unambiguous can still strand a pronoun in {language}, which orders its sentences differently and cannot always leave a subject implicit the way Italian does. Reread each sentence you changed: every pronoun in it must point, in {language}, to the person you mean and to no one else. Where one does not, write the name instead.
- Return exactly one summary per segment, in the original order. Do not merge, split or reorder them.
- These summaries are read straight through as well. Read yours through in {language} before returning them: they must follow one another as naturally there as the corrected Italian does.
- Write in {language}. Each summary is a single block of text with no line breaks."""


# The turns that follow the Italian one, in order. Each is a full pass over the
# canto in one language: the corrected Italian is already in the conversation.
TRANSLATION_TURNS = [
    ("en", "English", AlignedEnglish),
    ("ja", "Japanese", AlignedJapanese),
]

LANGS = ["it"] + [lang for lang, _, _ in TRANSLATION_TURNS]


def parse_canto_arg(value: str) -> Tuple[str, int]:
    m = re.fullmatch(r"(\w+):(\d+)", value.strip())
    if not m:
        raise argparse.ArgumentTypeError("expected part:canto, e.g. inferno:28")
    part = m.group(1)
    if part not in PARTS:
        raise argparse.ArgumentTypeError(f"unknown part '{part}'")
    return part, int(m.group(2))


def numbered(summaries: List[str]) -> str:
    return "\n".join(f"{i}. {text}" for i, text in enumerate(summaries, 1))


def dedup_canto(model: str, part: str, chapter_num: int,
                summaries: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Correct the canto's Italian summaries, then each translation, in one conversation.

    Returns {} if the model could not be made to return the right number of
    summaries. Each attempt starts a fresh conversation, so a retry never sees
    the discarded one.
    """
    total = len(summaries["it"])
    it_message = (f"[Current Italian summaries: {part.title()}, Canto {chapter_num}, "
                  f"{total} segments]\n{numbered(summaries['it'])}")

    for attempt in range(MAX_ATTEMPTS):
        client = Client(model=model, show_params=False)
        results: Dict[str, List[str]] = {}
        bad = None

        resp = client([it_message, INSTRUCTIONS_IT], schema=DedupedSummaries)
        results["it"] = [normalize(s) for s in resp.data.segments]
        if len(results["it"]) != total:
            bad = ("Italian", len(results["it"]))

        if bad is None:
            for lang, language, schema in TRANSLATION_TURNS:
                # The whole canto goes into each translation turn, unchanged
                # segments included, so that a rewritten passage keeps the
                # terminology the rest of the canto already uses
                message = f"[Current {language} summaries]\n{numbered(summaries[lang])}"
                resp = client([message, translation_instructions(language)], schema=schema)
                results[lang] = [normalize(s) for s in resp.data.segments]
                if len(results[lang]) != total:
                    bad = (language, len(results[lang]))
                    break

        if bad is None:
            return results

        language, got = bad
        print(f"  got {got} {language} summaries for {total} segments"
              f"{', retrying' if attempt < MAX_ATTEMPTS - 1 else ''}", file=sys.stderr)

    return {}


def report(lang: str, part: str, chapter_num: int, old: List[str], new: List[str]) -> int:
    """Print the segments that changed and return how many there were."""
    changed = 0
    for i, (before, after) in enumerate(zip(old, new), 1):
        if before == after:
            continue
        changed += 1
        print(f"\n{part} {chapter_num}:{i} ({lang})")
        print(f"  - {before}")
        print(f"  + {after}")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove cross-segment repetition from the segment summaries in "
                    "../it/{part}.md and carry the corrections into ../en/{part}.md "
                    "and ../ja/{part}.md, one canto at a time"
    )
    parser.add_argument("-m", "--model", required=True,
                        help="LLM model to use (e.g. openai:gpt-5.6-terra)")
    parser.add_argument("-c", "--canto", type=parse_canto_arg, action="append",
                        help="Limit to this canto (repeatable), e.g. inferno:28")
    parser.add_argument("-p", "--part", choices=PARTS, action="append",
                        help="Limit to this part (repeatable); default: all three, in order")
    parser.add_argument("--output-root", default="..",
                        help="Root directory containing it/, en/ and ja/ (default: ..)")
    parser.add_argument("--no-write", action="store_true",
                        help="Print the changes without writing them, for trying out "
                             "prompt changes against summaries already on disk")

    args = parser.parse_args()

    if args.canto and args.part:
        parser.error("--canto and --part are mutually exclusive")

    if args.canto:
        parts = list(dict.fromkeys(p for p, _ in args.canto))
    else:
        parts = args.part or PARTS

    total_changed = 0
    total_failed = 0

    for part in parts:
        paths = {lang: f"{args.output_root}/{lang}/{part}.md" for lang in LANGS}
        by_chapter = {lang: parse_summary_md(path) for lang, path in paths.items()}

        if args.canto:
            cantos = [n for p, n in args.canto if p == part]
        else:
            cantos = sorted(by_chapter["it"])

        for chapter_num in cantos:
            summaries = {lang: by_chapter[lang].get(chapter_num, []) for lang in LANGS}
            counts = {lang: len(s) for lang, s in summaries.items()}
            if not any(counts.values()):
                print(f"{part} {chapter_num}: not summarized yet, skipping")
                continue
            # The three {part}.md files are written as a matched set, so counts
            # that differ mean one of them has been damaged
            if len(set(counts.values())) != 1:
                sys.exit(f"{part} {chapter_num}: segment counts differ across languages "
                         + ", ".join(f"{lang}={n}" for lang, n in counts.items()))

            print(f"{part} {chapter_num} ({counts['it']} segments) -> ", end="", flush=True)
            results = dedup_canto(args.model, part, chapter_num, summaries)
            if not results:
                print("failed")
                total_failed += 1
                continue
            print("done")

            changed = 0
            for lang, result in results.items():
                n = report(lang, part, chapter_num, by_chapter[lang][chapter_num], result)
                if not n:
                    continue
                changed += n
                if args.no_write:
                    continue
                # Written per canto, so an interrupted run keeps what it has
                # already paid to generate
                by_chapter[lang][chapter_num] = result
                with open(paths[lang], "w", encoding="utf-8") as f:
                    f.write(format_summary_md(by_chapter[lang]))
            if not changed:
                print("  no repetition removed")
            total_changed += changed

    print(f"\nSegments changed: {total_changed}")
    if total_failed:
        print(f"Cantos failed: {total_failed}")
    if total_changed:
        print("Nothing written (--no-write)" if args.no_write
              else "Review with git diff; git checkout undoes the run")

    return 1 if total_failed else 0


if __name__ == "__main__":
    exit(main())
