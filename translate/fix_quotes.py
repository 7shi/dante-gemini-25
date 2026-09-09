"""Restore the quotation marks of an existing per-canto translation file.

translate_segments.py asks for one output line per source line, and nothing in
that arrangement carries the state of a speech across a line break: a speech
running over several lines can be closed early, reopened in the middle, or
never closed at all. The Italian source marks every speech with « », “ ” and
‘ ’, so the structure is already there - but it cannot be transposed
mechanically, because the target language's word order decides where in a line
an opening mark belongs, and a translation may legitimately merge or shift a
boundary the source draws inside a line.

Like align_lines.py, this script does not re-translate: it hands the model a
segment's source alongside its existing translation and asks for the same
translation back with only its quotation marks corrected. Unlike align_lines.py
it does not go through en.jsonl / ja.jsonl: the record it corrects is the
per-canto translation file itself (../en/{part}/NN.txt or ../ja/{part}/NN.txt),
which it rewrites in place, so there is no convert.py step afterward that
could overwrite a hand-fix made directly in that file.

A segment can begin or end in the middle of a speech - the source's quotes
balance within a chapter, not within every segment - so the prompt says to
leave a speech the source does not open or close alone.
"""

import argparse
import difflib
import os
import re
import sys
from typing import List, Tuple

from dante_corpus import QuoteSpan, canto as get_canto
from llm7shi import Client

from common.source import PARTS, canto_lines, load_segmentation

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# The language directory a file's path is found under, and the language name
# that goes into the prompt
LANGS = {"en": "English", "ja": "Japanese"}

INSTRUCTIONS = """The text above is an existing translation of the numbered source lines, one output line per source line. Its quotation marks are unreliable: the translation was made a segment at a time with no state carried across a line break, so a speech spanning several lines may be closed early, reopened in the middle, or never closed.

Your task is to correct the quotation marks and output every line again, prefixed with its source line number, one output line per source line, in order.

The source's « », “ ” and ‘ ’ are the authority for where a speech begins and ends. Map them by nesting level - the level decides the mark, not which character the source happens to use:

{guide}

Every speech the source opens must be opened in the translation, and every speech it closes must be closed.

A speech the source keeps open across several lines must run unbroken in the translation too. Where the translation closes it partway and opens it again, both marks go - the early closing one and the one that restarts the speech - so that it reads as one speech. Removing only one of the two leaves the rest of the segment unbalanced.

The translation also sets a phrase in quotation marks of its own accord now and then - for emphasis, or around a name or a title that the source leaves unmarked. Those marks open and close within one line and answer to nothing in the source: take them out. Never take out a mark that belongs to a speech the source does mark.

Where the source opens or closes in the middle of a line, put the mark where the translation's own word order calls for it, which is not always the same place.

Constraints:
- A segment may begin or end in the middle of a speech, which the source shows by closing a speech it never opened, or opening one it never closes. Leave it that way: never add an opening or a closing mark the source does not have.
- Every output line must be written in {target_lang}.
- Change nothing but the quotation marks. Reproduce every other character exactly - wording, punctuation, spelling and names - including anything you judge to be a mistranslation, an error or an awkward phrase. Correcting it is out of scope here.
- Keep one output line per source line. Never merge, split or drop a line to make the result read better.
- Output the numbered lines only. No commentary, no headings, no blank lines."""

GUIDES = {
    "English": "- the outermost quotation -> “ ”\n- a quotation inside it -> ‘ ’\n- one inside that -> “ ” again",
    "Japanese": "- the outermost quotation -> 「」\n- a quotation inside it -> 『』\n- one inside that -> 「」 again",
}

DEFAULT_GUIDE = "Use the quotation marks conventional in {target_lang}, alternating them by nesting level."

# The outermost pair per language, the only one the structural check counts:
# a nested mark never crosses a segment boundary, and in English the inner ’
# cannot be told from an apostrophe
OUTER_PAIR = {"English": "“”", "Japanese": "「」"}

# Every quote mark that does not belong to a language's own convention (see
# GUIDES) - the source's « » included, since the source is never the target.
# A leftover one means a conversion the model was supposed to make never
# happened, even if it balances and so passes the crossing check above
FOREIGN_CHARS = {
    "English": "«»「」『』",
    "Japanese": "«»“”‘’",
}

# Everything the model is allowed to touch, in the source and in either target
QUOTE_CHARS = "«»“”‘’「」『』\"'"

QUOTES = str.maketrans({c: None for c in QUOTE_CHARS})

LINE_RE = re.compile(r"^\s*(\d+)[.:)]?\s+(.*)$")


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).translate(QUOTES)


def has_quotes(text: str) -> bool:
    return any(c in QUOTE_CHARS for c in text)


def number_lines(numbers: List[int], lines: List[str]) -> str:
    return "\n".join(f"{no} {line}" for no, line in zip(numbers, lines))


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


def parse_segment_arg(value: str) -> List[int]:
    try:
        return [int(item) for item in value.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(
            "expected a segment number or a comma-separated list, e.g. 3 or 1,3"
        )


def parse_path(path: str) -> Tuple[str, str, int]:
    """The language, part and chapter a translation file's path names.

    Expects the site's own layout, e.g. ../en/inferno/01.txt: the language
    comes from the grandparent directory, the part from the parent directory,
    and the chapter from the leading digits of the filename.
    """
    abspath = os.path.abspath(path)
    part = os.path.basename(os.path.dirname(abspath))
    lang_dir = os.path.basename(os.path.dirname(os.path.dirname(abspath)))
    if part not in PARTS:
        raise ValueError(f"cannot tell which part this file belongs to (parent dir {part!r})")
    if lang_dir not in LANGS:
        raise ValueError(f"cannot tell which language this file belongs to (grandparent dir {lang_dir!r})")
    if not (m := re.match(r"(\d+)", os.path.basename(path))):
        raise ValueError("cannot tell which chapter this file is")
    return LANGS[lang_dir], part, int(m.group(1))


def flatten(spans) -> List[QuoteSpan]:
    out = []
    for span in spans:
        out.append(span)
        out.extend(flatten(span.children))
    return out


def crossing(spans: List[QuoteSpan], start: int, end: int) -> Tuple[int, int]:
    """Speeches the segment closes but does not open, and opens but does not close."""
    closes = sum(1 for s in spans if s.start_line < start <= s.end_line <= end)
    opens = sum(1 for s in spans if start <= s.start_line <= end < s.end_line)
    return closes, opens


def unmatched(lines: List[str], pair: str) -> Tuple[int, int]:
    """Marks the lines close without opening, and open without closing."""
    opens = closes = 0
    for line in lines:
        for c in line:
            if c == pair[0]:
                opens += 1
            elif c == pair[1]:
                if opens:
                    opens -= 1
                else:
                    closes += 1
    return closes, opens


def foreign_marks(lines: List[str], lang: str) -> str:
    """The lines' quote marks that do not belong to lang's own convention."""
    chars = FOREIGN_CHARS.get(lang, "")
    return "".join(sorted({c for line in lines for c in line if c in chars}))


def convert_outer_marks(lines: List[str], pair: str) -> List[str]:
    """Direct substitution of the source's «» for a target's outer pair.

    Safe only because «» always marks the source's outermost level and, for
    English, is the one literal source mark that can't be mistaken for the
    target's own: its deeper “ ” / ‘ ’ can be, since “ ” doubles as English's
    own outermost mark and ‘ ’ as an apostrophe - see FOREIGN_CHARS.

    Not attempted for Japanese at all, even though every level of the
    source's literal marks is unambiguous there: a leftover one usually
    means the segment was never actually translated - the Italian leaked
    through verbatim - rather than a quote-style slip, so converting it
    would launder that away instead of fixing it. Left for a human to
    re-translate; foreign_marks() keeps flagging it as a violation.
    """
    table = str.maketrans({"«": pair[0], "»": pair[1]})
    return [line.translate(table) for line in lines]


def mechanical_convert(lines: List[str], lang: str, pair: str) -> List[str] | None:
    """A deterministic fix for marks left in the source's own literal style -
    no model call needed, since remapping them to lang's convention has only
    one possible correct answer. None if lang has no such safe path, or the
    marks in `lines` aren't well-formed enough to trust mechanically.
    """
    if lang == "English" and pair:
        return convert_outer_marks(lines, pair)
    return None


def fix_segment(
    client: Client,
    numbers: List[int],
    source_lines: List[str],
    translation: str,
    source_lang: str,
    target_lang: str,
) -> str:
    guide = GUIDES.get(target_lang, DEFAULT_GUIDE.format(target_lang=target_lang))
    messages = [
        f"[Source text in {source_lang}, one numbered line per line]\n{number_lines(numbers, source_lines)}",
        f"[Existing {target_lang} translation of the text above]\n{number_lines(numbers, translation.split(chr(10)))}",
        INSTRUCTIONS.format(guide=guide, target_lang=target_lang),
    ]
    return client(messages).text.strip()


def check(numbers: List[int], source_lines: List[str], translation: str, response: str,
          pair: str, want: Tuple[int, int], lang: str) -> Tuple[List[str], float]:
    got_numbers, texts = parse_numbered(response)
    problems = []

    if got_numbers != numbers:
        if len(got_numbers) != len(numbers):
            problems.append(f"line count {len(got_numbers)} != {len(numbers)}")
        else:
            problems.append("line numbers do not match the source")

    # The source's quote spans say how many speeches the segment leaves open
    # or closes on its own; anything else means one was left unopened or
    # unclosed. Only the outermost pair is counted - see OUTER_PAIR
    if pair:
        got = unmatched(texts, pair)
        if got != want:
            problems.append(f"unmatched {pair} {got} != {want} (closes, opens)")

    # A mark that balances but never got converted to lang's own convention
    # (the source's « » left as is, say) would otherwise pass the check above
    if foreign := foreign_marks(texts, lang):
        problems.append(f"leftover {foreign} not converted to {lang}'s quotation marks")

    before, after = normalize(translation), normalize("\n".join(texts))
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    drift = 0.0 if before == after else 1.0 - matcher.ratio()
    if drift:
        problems.append("text changed apart from the quotation marks")

    return problems, drift


def load_translation(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def save_translation(path: str, lines: List[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore the quotation marks of an existing translation"
    )
    parser.add_argument("files", nargs="+",
                        help="Per-canto translation files to fix in place (e.g. ../en/inferno/01.txt)")
    parser.add_argument("-m", "--model",
                        help="LLM model to use (e.g. openai:gpt-5.6-terra). Required unless --check")
    parser.add_argument("-s", "--segment", type=parse_segment_arg,
                        help="Process only these segments of each canto, comma separated "
                             "(e.g. 3 or 1,3). Without it, every segment whose source or "
                             "translation holds a quotation mark is processed")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="Report the changes without writing them back")
    parser.add_argument("--check", action="store_true",
                        help="Report which segments' quotation marks already mismatch what "
                             "the source's structure calls for, without calling the model or "
                             "writing anything - use it to locate a problem left over from a "
                             "previous run whose output has scrolled away")

    args = parser.parse_args()
    if not args.check and not args.model:
        parser.error("-m/--model is required unless --check is given")

    # Segments are independent, so no turn is carried over into the next
    client = None if args.check else Client(
        model=args.model, show_params=len(args.files) == 1, keep_history=False)

    violations: List[Tuple[str, List[str], float]] = []
    changed = processed = mech_changed = mech_processed = 0

    for path in args.files:
        try:
            lang, part, chapter = parse_path(path)
            source_lines = canto_lines(part, chapter)
            boundaries = load_segmentation(
                os.path.join(SCRIPT_DIR, "segments", f"{part}.jsonl"))[chapter]["boundaries"]
            translation_lines = load_translation(path)
        except (OSError, ValueError, KeyError) as e:
            print(f"{path}: {e}", file=sys.stderr)
            return 1

        if len(translation_lines) != len(source_lines):
            print(f"{path}: line count {len(translation_lines)} != source's {len(source_lines)}",
                  file=sys.stderr)
            return 1

        spans = flatten(get_canto(part, chapter).quotes())
        pair = OUTER_PAIR.get(lang, "")

        for segment, b in enumerate(boundaries, 1):
            if args.segment and segment not in args.segment:
                continue

            start, end = b["start_line"], b["end_line"]
            part_slice = slice(start - 1, end)
            numbers = list(range(start, end + 1))
            seg_source = source_lines[part_slice]
            seg_translation = translation_lines[part_slice]

            # A segment without a quotation mark on either side has nothing to fix
            if not has_quotes("".join(seg_source + seg_translation)):
                continue
            label = f"{part} {chapter:2d}:{segment}"
            want = crossing(spans, start, end) if pair else (0, 0)

            # Same structural checks fix_segment's response is held to below,
            # run directly on the translation as it stands on disk. Without a
            # known outer pair (an unrecognized target language) crossing
            # can't be verified, so nothing is ever considered already correct
            got = unmatched(seg_translation, pair) if pair else None
            foreign = foreign_marks(seg_translation, lang)
            already_ok = bool(pair) and got == want and not foreign

            if args.check:
                if not already_ok:
                    problems = []
                    if pair and got != want:
                        problems.append(f"unmatched {pair} {got} != {want} (closes, opens)")
                    if foreign:
                        problems.append(f"leftover {foreign} not converted to {lang}'s quotation marks")
                    violations.append((label, problems, 0.0))
                    print(f"{label} (lines {start}-{end}): {', '.join(problems)}")
                continue

            # Already matches the source's structure - sending it to the model
            # would only risk it introducing a mark that breaks that match
            if already_ok:
                continue

            # In Japanese a leftover literal source mark usually means the
            # segment was never actually translated, not a quote-style slip -
            # skip it entirely rather than have fix_segment "correct" the
            # quotes on text that is still Italian. foreign_marks() keeps
            # flagging it via --check until it is redone by hand
            if foreign and lang == "Japanese":
                print(f"{label} (lines {start}-{end}): leftover {foreign} - "
                      f"likely untranslated, skipping")
                continue

            # A leftover literal source mark otherwise has only one correct
            # target rendering, so try that deterministically before
            # spending a model call on it
            if foreign:
                mechanical = mechanical_convert(seg_translation, lang, pair)
                if mechanical is not None and (not pair or unmatched(mechanical, pair) == want) \
                        and not foreign_marks(mechanical, lang):
                    print(f"{label} (lines {start}-{end}): mechanically converted {foreign}")
                    mech_changed += sum(a != b for a, b in zip(seg_translation, mechanical))
                    translation_lines[part_slice] = mechanical
                    mech_processed += 1
                    if not args.dry_run:
                        save_translation(path, translation_lines)
                    continue

            print(f"\n{label} -> fixing quotation marks (lines {start}-{end})")

            translation = "\n".join(seg_translation)
            response = fix_segment(client, numbers, seg_source, translation, "Italian", lang)

            problems, drift = check(numbers, seg_source, translation, response, pair, want, lang)
            if problems:
                violations.append((label, problems, drift))
                print(f"  violation: {', '.join(problems)}")
                print("  left unchanged")
                continue
            print(f"  drift: {drift * 100:.1f}%")

            _, texts = parse_numbered(response)
            changed += sum(a != b for a, b in zip(seg_translation, texts))
            translation_lines[part_slice] = texts
            processed += 1

            if not args.dry_run:
                save_translation(path, translation_lines)

    if args.check:
        print(f"\n{len(violations)} segment(s) already mismatch the source's structure")
    else:
        print(f"\nMechanically converted {mech_processed} segments, {mech_changed} lines changed")
        print(f"Processed {processed} segments, {changed} lines changed"
              + (" (dry run, nothing written)" if args.dry_run else ""))
        print(f"Violations: {len(violations)}/{processed + len(violations)}")
        for label, problems, drift in violations:
            print(f"  {label} {', '.join(problems)} (drift {drift * 100:.1f}%)")

    return 0


if __name__ == "__main__":
    exit(main())
