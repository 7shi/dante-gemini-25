# Italian Source

This directory holds the Italian source text and the pipeline stage that
splits it into per-canto files, consumed by the translation pipeline in
[`../translate/`](../translate/README.md).

## Pipeline

1. **Download the source text** (`make` in this directory)

   Fetches `pg1000.txt` from [Project Gutenberg](https://www.gutenberg.org/ebooks/1000).

2. **Split into per-canto files** (`make split`)

   `split_source.py` reads `pg1000.txt` from stdin and writes one text file
   per canto under `inferno/`, `purgatorio/`, and `paradiso/`
   (e.g. `inferno/01.txt`).

For segmenting, translating, and everything downstream, see
[`../translate/README.md`](../translate/README.md).

## Other files

- `pg1000.txt` - Downloaded Italian source text (gitignored).
- `inferno/`, `purgatorio/`, `paradiso/` - Per-canto Italian text files
  produced by `split_source.py` (gitignored).
