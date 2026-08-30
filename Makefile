.PHONY: help all clean check \
        convert convert-en convert-ja \
		summarize1 summarize1-en summarize1-ja

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  all              Run 'convert' and 'summarize1'"
	@echo "  clean            Remove generated en/ and ja/"
	@echo "  check            Run check.py"
	@echo "  convert          Convert JSONL (en + ja)"
	@echo "  convert-en       Convert en.jsonl to en/"
	@echo "  convert-ja       Convert ja.jsonl to ja/"
	@echo "  summarize1       Generate one-line summaries (en + ja, LLM)"
	@echo "  summarize1-en    Generate one-line summaries from en.jsonl to en/"
	@echo "  summarize1-ja    Generate one-line summaries from ja.jsonl to ja/"

all: convert summarize1

clean:
	rm -rf en/ ja/

check:
	uv run check.py

convert: convert-en convert-ja

convert-en convert-ja: convert-%: %.jsonl
	uv run convert.py $< --output-dir $*

summarize1: summarize1-en summarize1-ja

summarize1-en summarize1-ja: summarize1-%: %.jsonl
	uv run summarize1.py -m gemini-2.5-pro $< --output-dir $*
