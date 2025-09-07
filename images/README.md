# Image Generation Scripts

This directory contains scripts used to generate images for Dante's Divine Comedy project using Nano Banana.

## Overview

The image generation process involves two main steps:

1. **Reference Image Generation**: Using `characters.txt`, reference images of the main characters (Dante, Virgil, and Beatrice) are generated to establish consistent character designs.

2. **Chapter Illustrations**: Reference images and chapter summaries are passed together to generate illustrations for specific chapters of the Divine Comedy.

## Files

- **`characters.txt`**: Contains the detailed prompt for generating the reference image of the three main characters from Dante's Divine Comedy
- **`generate-image.py`**: Python script that generates chapter illustrations using the reference image and chapter summaries

## Character Reference Image

The reference image contains three iconic figures:
- **Dante**: Man in red robes with laurel crown (left figure)
- **Virgil**: Older man with halo in earth-toned robes (center figure)  
- **Beatrice**: Woman in white robes with golden light (right figure)

## Usage

The `generate-image.py` script can be used to generate illustrations for chapters of the Divine Comedy:

```bash
python generate-image.py <reference_image> [options]
```

### Options:
- `-p, --parts`: Specify parts to process (inferno, purgatorio, paradiso)
- `-c, --chapters`: Specify specific chapters to process
- `--append`: Add new images even if files already exist
- `--title`: Use prompt from specified file instead of chapter summaries
- `--characters`: Comma-separated list of characters to include

### Examples:

```bash
# Generate images for all chapters using dante.jpg as reference
python generate-image.py dante.jpg

# Generate images for specific chapters of Inferno
python generate-image.py dante.jpg -p inferno -c 1

# Generate image with specific characters
python generate-image.py dante.jpg --characters "Dante,Beatrice"
```

## Dependencies

- PIL (Python Imaging Library)
- Nano Banana module (imported from parent directory)

## Process

1. The script reads chapter summaries from text files in part directories (inferno, purgatorio, paradiso)
2. Creates prompts combining chapter summaries with character reference information
3. Uses the Nano Banana `generate_and_save_image` function to create illustrations
4. Saves generated images with sequential numbering (e.g., `01-1.jpg`, `01-2.jpg`)

The generated illustrations maintain consistency with the reference character designs while depicting key scenes and moments from each chapter in a classical Renaissance art style inspired by Gustave Doré's Divine Comedy illustrations.
