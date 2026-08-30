.PHONY: help all clean check \
        convert convert-en convert-ja

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  all              Run 'convert'"
	@echo "  clean            Remove generated en/ and ja/"
	@echo "  check            Run check.py"
	@echo "  convert          Convert JSONL (en + ja)"
	@echo "  convert-en       Convert en.jsonl to en/"
	@echo "  convert-ja       Convert ja.jsonl to ja/"

all: convert

clean:
	rm -rf en/ ja/

check:
	uv run check.py

convert: convert-en convert-ja

convert-en convert-ja: convert-%: %.jsonl
	uv run convert.py $< --output-dir $*
