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
