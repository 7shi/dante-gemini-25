"""Compress the illustrations in images/ for the static site.

Reads the selected (un-suffixed) images from images/ and writes size-capped
JPEGs to dist/images/, mirroring the source layout:

  images/dante.jpg               -> dist/images/dante.jpg
  images/{part}-title.jpg        -> dist/images/{part}-title.jpg
  images/{part}-last.jpg         -> dist/images/{part}-last.jpg
  images/{part}/NN.jpg           -> dist/images/{part}/NN.jpg

Already-compressed outputs are skipped unless --force is given.
"""

import argparse
from pathlib import Path
from PIL import Image

MAX_SIZE = 50 * 1024
TARGET_WIDTH = 1024

PARTS = ["inferno", "purgatorio", "paradiso"]
ROOT = Path(__file__).parent
DIST_IMAGES = ROOT.parent / "dist" / "images"


def compress(src_path: Path, dst_path: Path):
    """Saves src_path as a JPEG under MAX_SIZE bytes, shrinking quality/size as needed."""
    image = Image.open(src_path).convert("RGB")
    if image.width > TARGET_WIDTH:
        height = round(image.height * TARGET_WIDTH / image.width)
        image = image.resize((TARGET_WIDTH, height))
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    for quality in range(85, 4, -5):
        image.save(dst_path, "JPEG", quality=quality)
        if dst_path.stat().st_size <= MAX_SIZE:
            return
    while dst_path.stat().st_size > MAX_SIZE:
        image = image.resize((image.width * 9 // 10, image.height * 9 // 10))
        image.save(dst_path, "JPEG", quality=70)


def source_files():
    """Yields (src_path, dst_relative_path) for every image the site needs."""
    yield ROOT / "dante.jpg", Path("dante.jpg")
    for part in PARTS:
        yield ROOT / f"{part}-title.jpg", Path(f"{part}-title.jpg")
        yield ROOT / f"{part}-last.jpg", Path(f"{part}-last.jpg")
        part_dir = ROOT / part
        if part_dir.is_dir():
            for jpg in sorted(part_dir.glob("[0-9][0-9].jpg")):
                yield jpg, Path(part) / jpg.name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Recompress images even if the output already exists")
    args = parser.parse_args()

    missing = []
    compressed = 0
    for src_path, rel_path in source_files():
        dst_path = DIST_IMAGES / rel_path
        if not src_path.exists():
            missing.append(src_path)
            continue
        if dst_path.exists() and not args.force:
            continue
        compress(src_path, dst_path)
        print(f"{src_path.relative_to(ROOT.parent)} -> {dst_path.relative_to(ROOT.parent)} ({dst_path.stat().st_size} bytes)")
        compressed += 1

    if missing:
        print("Missing source images (see images/README.md for how these are put in place):")
        for path in missing:
            print(f"  {path.relative_to(ROOT.parent)}")
        raise SystemExit(1)

    print(f"Compressed {compressed} image(s); already up to date otherwise.")


if __name__ == "__main__":
    main()
