# Image Generation Scripts

This directory contains scripts used to generate the illustrations for Dante's
Divine Comedy project using Nano Banana (Gemini image generation).

## Tracked vs. generated

Scripts and prompts are tracked in git; the images themselves are not (see
`.gitignore`). They are large (~15MB in total) and are put in place
out-of-band (not via this Makefile). Once in place, `make` (or any of
`reference` / `illustrations` / `titles`) sees the files already exist and
does nothing, so it never calls the image-generation API by accident.

```
images/
  Makefile               tracked  - the (idle, once the images are in place) generation chain
  banana.py               tracked  - Gemini image-generation core (retry logic, Sixel preview)
  generate-image.py       tracked  - generates chapter illustrations / title images
  generate-reference.py   tracked  - generates the character reference images
  characters.txt          tracked  - prompt for the initial 3-character reference image
  {part}-title.txt        tracked  - prompt for each part's title illustration
  {part}-last.txt         tracked  - prompt for each part's final-scene illustration
  dante.jpg               ignored  - initial reference image (Dante, Virgil, Beatrice)
  dante-virgil.jpg        ignored  - white-background reference: Dante + Virgil
  dante-beatrice.jpg      ignored  - white-background reference: Dante + Beatrice
  dante-3.jpg             ignored  - white-background reference: all three
  {part}-title.jpg        ignored  - selected title illustration
  {part}-last.jpg         ignored  - selected final-scene illustration
  {part}/NN.txt           ignored  - prompt for canto NN (one line per translated segment)
  {part}/NN.jpg           ignored  - selected illustration for canto NN
```

`{part}` is one of `inferno`, `purgatorio`, `paradiso`.

## Pipeline

1. **Reference image** (`characters.txt` -> `dante.jpg`): a single prompt
   describing all three characters (Dante, Virgil, Beatrice) together,
   generated with no input image.
2. **Character subsets** (`dante.jpg` -> `dante-virgil.jpg` /
   `dante-beatrice.jpg` / `dante-3.jpg`): `generate-reference.py` re-renders
   the chosen subset of characters against a plain white background, so later
   prompts have a clean, consistent character sheet to reference.
3. **Canto prompts** (`{part}/NN.txt`): one line per translated segment's
   summary for that canto, used as the illustration prompt. These were
   generated from the English translations (`../en.jsonl`) at the time the
   images were made; note that inferno 26, purgatorio 30, and paradiso 8 were
   later re-translated (see the top-level README), so their current
   `en.jsonl` summaries no longer match the `.txt` files here verbatim.
4. **Illustrations** (`{part}/NN.jpg`): `generate-image.py` combines a canto's
   prompt with the appropriate character reference image
   (`dante-virgil.jpg` for inferno/purgatorio, `dante-beatrice.jpg` for
   paradiso) to produce the chapter illustration.
5. **Title / final-scene images** (`{part}-title.jpg`, `{part}-last.jpg`):
   same mechanism as step 4, but driven by a single hand-written prompt file
   (`{part}-title.txt` / `{part}-last.txt`) instead of a canto's summary.

Multiple candidates are generated per target with a numeric suffix
(`01-1.jpg`, `01-2.jpg`, ...); the one judged best is copied over without a
suffix (`01.jpg`). Both `generate-image.py` and `generate-reference.py` treat
the existence of the un-suffixed file as "already selected" and skip
regeneration unless `--append` (or, for `generate-reference.py`, `--force`)
is given.

## Usage

```bash
make          # no-op once the images/prompts are in place: everything already exists
make -n       # sanity check: prints nothing once everything is in place
```

To regenerate a single missing piece from scratch (e.g. after removing a
selected file), the individual scripts can be run directly:

```bash
uv run generate-reference.py -o dante.jpg --prompt-file characters.txt
uv run generate-reference.py dante.jpg -o dante-virgil.jpg --characters Dante,Virgil
uv run generate-image.py dante-virgil.jpg -p inferno -c 1
uv run generate-image.py dante-virgil.jpg -p inferno --title inferno-title.txt
```

### `generate-image.py` options

- `-p, --parts`: parts to process (`inferno`, `purgatorio`, `paradiso`)
- `-c, --chapters`: specific chapter numbers
- `--append`: add another candidate even if a selected image already exists
- `--title`: use a prompt file instead of a chapter's summaries (for title /
  final-scene images)
- `--characters`: comma-separated character subset (default: `Dante,Virgil`)

### `generate-reference.py` options

- `input_image`: source reference image (omit together with `--prompt-file`)
- `-o, --output`: output image path
- `--characters`: comma-separated character subset to render
- `--prompt-file`: generate straight from a prompt file instead of an input
  image + character subset (used for the initial `dante.jpg`)
- `--force`: regenerate even if the output already exists

## Dependencies

- PIL (Python Imaging Library)
- Google Generative AI (`google-genai`)
- Sixel converter for terminal image display
- Nano Banana module (local `banana.py`)

The module requires a `GEMINI_API_KEY` environment variable to authenticate
with Google's Gemini API.
