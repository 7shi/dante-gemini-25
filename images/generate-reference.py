import argparse
import os
from PIL import Image
from banana import generate_and_save_image

character_details = {
    "Dante": "Man in red robes with laurel crown",
    "Virgil": "Older man with halo in earth-toned robes",
    "Beatrice": "Woman in white robes with golden light",
}

def create_character_explanations(*characters):
    return "\n".join(f"- {character}: {character_details[character]}" for character in characters)

def create_reference_prompt(*characters):
    names = " and ".join(characters) if len(characters) < 3 else ", ".join(characters[:-1]) + f", and {characters[-1]}"
    explanations = create_character_explanations(*characters)
    return f"""Create an image with {names} standing side by side against a pure white background:
{explanations}

Maintain their character designs from the original image but arrange them in a clean composition with white background."""

def main():
    parser = argparse.ArgumentParser(
        description="Generate a white-background reference image for a subset of characters, "
                     "or (with --prompt-file, no input image) the initial full-scene reference image"
    )
    parser.add_argument("input_image", nargs="?", help="Input image file path (source character reference)")
    parser.add_argument("-o", "--output", dest="output_image", required=True, help="Output image file path")
    parser.add_argument("--characters", type=str,
                         help="Comma-separated list of characters to include (from Dante, Virgil, Beatrice); "
                              "required when input_image is given")
    parser.add_argument("--prompt-file", type=str,
                         help="Generate from this prompt file instead of an input image + character subset "
                              "(used to create the initial dante.jpg from characters.txt)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if the output already exists")
    args = parser.parse_args()

    if not args.force and os.path.exists(args.output_image):
        print(f"Skipping {args.output_image} (already exists, use --force to regenerate)")
        return

    if args.prompt_file:
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            prompt = f.read().strip()
        contents = [prompt]
    else:
        if not args.input_image or not args.characters:
            parser.error("input_image and --characters are required unless --prompt-file is given")
        prompt = create_reference_prompt(*(c.strip() for c in args.characters.split(",")))
        try:
            image = Image.open(args.input_image)
        except FileNotFoundError:
            print(f"Error: {args.input_image} not found.")
            exit(1)
        contents = [prompt, image]

    success = generate_and_save_image(contents, args.output_image)

    if not success:
        print("No image was returned from the model.")

if __name__ == "__main__":
    main()
