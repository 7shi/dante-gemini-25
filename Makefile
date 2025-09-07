.PHONY: all clean convert-en convert-ja

all: convert-en convert-ja

convert-en: en.jsonl
	python convert.py $< --output-dir en

convert-ja: ja.jsonl
	python convert.py $< --output-dir ja

clean:
	rm -rf en/ ja/
