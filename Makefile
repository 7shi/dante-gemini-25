.PHONY: all convert-en convert-ja clean check

all: convert-en convert-ja

convert-en: en.jsonl
	python convert.py $< --output-dir en

convert-ja: ja.jsonl
	python convert.py $< --output-dir ja

clean:
	rm -rf en/ ja/

check:
	python check.py
