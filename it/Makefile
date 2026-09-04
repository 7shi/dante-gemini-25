.PHONY: help all split segment1 segment2 segment3 \
        translate-en translate-ja align align-en align-ja \
        convert convert-en convert-ja summarize1 summarize1-en summarize1-ja \
        check

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  all              Download pg1000.txt"
	@echo "  split            Split pg1000.txt into per-canto files"
	@echo "  segment1/2/3     Segment inferno/purgatorio/paradiso into inferno.jsonl/purgatorio.jsonl/paradiso.jsonl"
	@echo "  translate-en     Translate segments to English into ../en.jsonl"
	@echo "  translate-ja     Translate segments to Japanese into ../ja.jsonl"
	@echo "  align            Fix line-count mismatches in ../en.jsonl and ../ja.jsonl"
	@echo "  align-en         Fix line-count mismatches in ../en.jsonl"
	@echo "  align-ja         Fix line-count mismatches in ../ja.jsonl"
	@echo "  convert          Expand ../en.jsonl and ../ja.jsonl into ../en/ and ../ja/"
	@echo "  convert-en       Expand ../en.jsonl into ../en/"
	@echo "  convert-ja       Expand ../ja.jsonl into ../ja/"
	@echo "  summarize1       Generate one-line summaries (../en/ + ../ja/, LLM)"
	@echo "  summarize1-en    Generate one-line summaries from ../en.jsonl into ../en/"
	@echo "  summarize1-ja    Generate one-line summaries from ../ja.jsonl into ../ja/"
	@echo "  check            Check segment line counts match across it/en/ja"
	@echo ""
	@echo "convert/summarize1 overwrite the hand-edited ../en/ and ../ja/ trees."

URL = https://www.gutenberg.org/ebooks/1000
TARGET = pg1000.txt

all: $(TARGET)

$(TARGET):
	wget --trust-server-names $(URL).txt.utf-8

split: $(TARGET)
	python split_source.py < $(TARGET)

SEGMENT = uv run segment_chapters.py -m gemini-2.5-pro

segment1:
	$(SEGMENT) -o inferno.jsonl inferno
segment2:
	$(SEGMENT) -o purgatorio.jsonl purgatorio
segment3:
	$(SEGMENT) -o paradiso.jsonl paradiso

TRANSLATE = uv run translate_segments.py -m gemini-2.5-pro

translate-en:
	$(TRANSLATE) -o ../en.jsonl inferno purgatorio paradiso -f Italian -t English
translate-ja:
	$(TRANSLATE) -o ../ja.jsonl inferno purgatorio paradiso -f Italian -t Japanese

ALIGN_MODEL = openai:gpt-5.6-terra

# align_lines.py fixes only the segments whose line count doesn't match the
# source; re-run after a translate pass to detect and reflow the mismatches.
align: align-en align-ja

align-en:
	uv run align_lines.py ../en.jsonl -m $(ALIGN_MODEL)
align-ja:
	uv run align_lines.py ../ja.jsonl -m $(ALIGN_MODEL)

# convert/summarize1 regenerate ../en/ and ../ja/ from the JSONL, overwriting
# any hand-fix made directly in those expanded files. Run deliberately.

convert: convert-en convert-ja

convert-en convert-ja: convert-%: ../%.jsonl
	uv run convert.py $< --output-dir ../$*

summarize1: summarize1-en summarize1-ja

summarize1-en summarize1-ja: summarize1-%: ../%.jsonl
	uv run summarize1.py -m gemini-2.5-pro $< --output-dir ../$*

check:
	uv run check.py
