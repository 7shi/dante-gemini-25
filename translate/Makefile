.PHONY: help segment1 segment2 segment3 \
        translate-en translate-ja align align-en align-ja \
        convert convert-en convert-ja \
        summarize summarize1 \
        dedup check

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  segment1/2/3     Segment inferno/purgatorio/paradiso into segments/inferno.jsonl/purgatorio.jsonl/paradiso.jsonl"
	@echo "  translate-en     Translate segments to English into ../en.jsonl"
	@echo "  translate-ja     Translate segments to Japanese into ../ja.jsonl"
	@echo "  align            Fix line-count mismatches in ../en.jsonl and ../ja.jsonl"
	@echo "  align-en         Fix line-count mismatches in ../en.jsonl"
	@echo "  align-ja         Fix line-count mismatches in ../ja.jsonl"
	@echo "  convert          Expand ../en.jsonl and ../ja.jsonl into ../en/ and ../ja/"
	@echo "  convert-en       Expand ../en.jsonl into ../en/"
	@echo "  convert-ja       Expand ../ja.jsonl into ../ja/"
	@echo "  summarize        Regenerate ../it/../en/../ja/*.md as a matched trilingual set (LLM)"
	@echo "  summarize1       Regenerate ../it/../en/../ja/*-1.md as a matched trilingual set (LLM)"
	@echo "  dedup            Remove cross-segment repetition from ../it/../en/../ja/*.md (LLM)"
	@echo "  check            Check segment line counts match across it/en/ja"
	@echo ""
	@echo "convert overwrites the hand-edited ../en/ and ../ja/ translation .txt files."
	@echo "summarize/summarize1 are resumable: interrupt and re-run to continue where left off."

MODEL = gemini-2.5-pro

SEGMENT = uv run segment_chapters.py -m $(MODEL)

segment1:
	$(SEGMENT) -o segments/inferno.jsonl ../it/inferno
segment2:
	$(SEGMENT) -o segments/purgatorio.jsonl ../it/purgatorio
segment3:
	$(SEGMENT) -o segments/paradiso.jsonl ../it/paradiso

TRANSLATE = uv run translate_segments.py -m $(MODEL)

translate-en:
	$(TRANSLATE) -o ../en.jsonl ../it/inferno ../it/purgatorio ../it/paradiso -f Italian -t English
translate-ja:
	$(TRANSLATE) -o ../ja.jsonl ../it/inferno ../it/purgatorio ../it/paradiso -f Italian -t Japanese

ALIGN_MODEL = openai:gpt-5.6-terra

# align_lines.py fixes only the segments whose line count doesn't match the
# source; re-run after a translate pass to detect and reflow the mismatches.
align: align-en align-ja

align-en:
	uv run align_lines.py ../en.jsonl -m $(ALIGN_MODEL)
align-ja:
	uv run align_lines.py ../ja.jsonl -m $(ALIGN_MODEL)

# convert regenerates ../en/ and ../ja/'s translation .txt files from the
# JSONL, overwriting any hand-fix made directly in those files. Run
# deliberately.

convert: convert-en convert-ja

convert-en convert-ja: convert-%: ../%.jsonl
	uv run convert.py $< --output-dir ../$*

SUMMARIZE_MODEL = google:$(MODEL)

# summarize_segments.py regenerates ../it/../en/../ja/{part}.md from scratch as
# a matched trilingual set, replacing the old (mismatched) en/ja-only summaries
# expanded by convert.py. Resumable: it reads back whatever's already in those
# files and continues from there, so an interrupted run just needs a re-run.
summarize:
	uv run summarize_segments.py -m $(SUMMARIZE_MODEL)

# summarize1.py derives one-line-per-canto summaries from summarize's
# {part}.md segment summaries (not from the JSONL), one canto at a time as a
# matched trilingual set. Cantos summarize hasn't reached yet are skipped and
# picked up on a later run.
summarize1:
	uv run summarize1.py -m $(SUMMARIZE_MODEL)

DEDUP_MODEL = $(ALIGN_MODEL)

# dedup_summaries.py rewrites one canto's Italian segment summaries to drop
# what a later segment restates from an earlier one, then carries the same
# edits into ../en/{part}.md and ../ja/{part}.md in later turns of the same
# conversation, keeping the three files a matched set.
#
# For a canto you have judged repetitive, not for a pass over everything -
# a full run was tried and dropped as not worth it (see README.md).
#
# It writes as it goes - there is no dry run, since the edit can't be known
# without generating it. Commit first; review with git diff.
#
#   make dedup ARGS='-c inferno:28'
#   make dedup ARGS='-p inferno'
dedup:
	uv run dedup_summaries.py -m $(DEDUP_MODEL) $(ARGS)

check:
	uv run check.py
