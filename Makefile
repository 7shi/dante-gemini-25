.PHONY: help clean-dist build images serve deploy release

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  clean-dist       Remove dist/"
	@echo "  build            Build the static site into dist/ (see templates/README.md)"
	@echo "  images           Compress images/ illustrations into dist/images/"
	@echo "  serve            Serve dist/ locally at http://localhost:8000"
	@echo "  deploy           Build and publish dist/ to the gh-pages branch"
	@echo "  release          Package en.jsonl/ja.jsonl/images into release/*.zip"
	@echo ""
	@echo "For the translation pipeline (convert/summarize1/check/...), see it/README.md."

clean-dist:
	rm -rf dist

build: images
	uv run templates/build.py

images:
	uv run images/compress.py

serve:
	cd dist && uv run python -m http.server 8000

deploy: build
	bash templates/deploy.sh

release:
	mkdir -p release
	zip -j release/en.zip en.jsonl
	zip -j release/ja.zip ja.jsonl
	cd images && git ls-files --others --ignored --exclude-standard | grep -v '^__pycache__/' | zip ../release/images.zip -@
