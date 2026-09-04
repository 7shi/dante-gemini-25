.PHONY: help all split

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  all              Download pg1000.txt"
	@echo "  split            Split pg1000.txt into per-canto files"
	@echo ""
	@echo "For the translation pipeline (segment/translate/convert/summarize1/check/...), see ../translate/README.md."

URL = https://www.gutenberg.org/ebooks/1000
TARGET = pg1000.txt

all: $(TARGET)

$(TARGET):
	wget --trust-server-names $(URL).txt.utf-8

split: $(TARGET)
	python split_source.py < $(TARGET)
