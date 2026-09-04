.PHONY: help all clean clean-dist check \
        convert convert-en convert-ja \
		summarize1 summarize1-en summarize1-ja \
		build images serve deploy

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  all              Run 'convert' and 'summarize1'"
	@echo "  clean            Remove generated en/ and ja/"
	@echo "  clean-dist       Remove dist/"
	@echo "  check            Run check.py"
	@echo "  convert          Convert JSONL (en + ja)"
	@echo "  convert-en       Convert en.jsonl to en/"
	@echo "  convert-ja       Convert ja.jsonl to ja/"
	@echo "  summarize1       Generate one-line summaries (en + ja, LLM)"
	@echo "  summarize1-en    Generate one-line summaries from en.jsonl to en/"
	@echo "  summarize1-ja    Generate one-line summaries from ja.jsonl to ja/"
	@echo "  build            Build the static site into dist/ (see templates/README.md)"
	@echo "  images           Compress images/ illustrations into dist/images/"
	@echo "  serve            Serve dist/ locally at http://localhost:8000"
	@echo "  deploy           Build and publish dist/ to the gh-pages branch"

all: convert summarize1

clean:
	rm -rf en/ ja/

clean-dist:
	rm -rf dist

check:
	uv run check.py

convert: convert-en convert-ja

convert-en convert-ja: convert-%: %.jsonl
	uv run convert.py $< --output-dir $*

summarize1: summarize1-en summarize1-ja

summarize1-en summarize1-ja: summarize1-%: %.jsonl
	uv run summarize1.py -m gemini-2.5-pro $< --output-dir $*

build: images
	uv run templates/build.py

images:
	uv run images/compress.py

serve:
	cd dist && uv run python -m http.server 8000

deploy: build
	bash templates/deploy.sh
