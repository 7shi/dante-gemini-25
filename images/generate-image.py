import argparse
import os
import sys
from PIL import Image
from banana import generate_and_save_image

def read_chapter_summaries(part, chapter):
    """Read summaries for a specific chapter"""
    chapter_file = os.path.join(part, f"{chapter:02d}.txt")
    if not os.path.exists(chapter_file):
        return None
    
    with open(chapter_file, 'r', encoding='utf-8') as f:
        summaries = [line.strip() for line in f if line.strip()]
    
    return summaries

character_details = {
    "Dante": "Man in red robes with laurel crown (left figure)",
    "Virgil": "Older man with halo in earth-toned robes (center figure)",
    "Beatrice": "Woman in white robes with golden light (right figure)",
}

def create_character_explanations(*characters):
    return "\n".join(f"- {character}: {character_details[character]}" for character in characters)

def create_illustration_prompt(part, chapter, combined_summary, characters=None):
    """Create a prompt for generating chapter illustration"""
    if characters is None:
        characters = ["Dante", "Virgil"]
    
    chapter_prompt = f"Chapter {chapter} of " if chapter else ""
    characters_prompt = create_character_explanations(*characters)
    return f"""Create an illustration for {chapter_prompt}Dante's {part.title()} in a classical Renaissance art style. 

Chapter summary: {combined_summary}

Reference image contains three main characters:
{characters_prompt}

Style requirements:
- Classical Renaissance painting style similar to Gustave Doré's Divine Comedy illustrations
- Dramatic lighting and composition
- Rich, deep colors appropriate to the scene
- Include appropriate characters from the reference image based on the chapter content
- Maintain the exact character designs and appearance from the reference image
- Focus on the key dramatic moment or scene from this chapter
- Atmospheric and symbolic elements that reflect the spiritual journey"""

def generate_single_image(prompt, reference_image, output_filename):
    """Generate a single image with error handling"""
    contents = [prompt, reference_image]
    try:
        success = generate_and_save_image(contents, output_filename)
    except Exception as e:
        print(e)
        success = False
    
    if success:
        print(f"  ✓ Generated: {output_filename}")
    else:
        print(f"  ✗ Failed to generate: {output_filename}")
    
    return success

def process_part(part, chapters, reference_image, append, characters=None):
    """Process a single part (inferno, purgatorio, paradiso)"""
    if not os.path.exists(part):
        print(f"Warning: Directory '{part}' not found, skipping.")
        return 0
    
    # Get available chapters
    chapter_files = [f for f in os.listdir(part) if f.endswith('.txt')]
    available_chapters = sorted([int(f.split('.')[0]) for f in chapter_files])
    
    # Use specified chapters or all available
    target_chapters = chapters if chapters else available_chapters
    
    total_generated = 0
    
    for chapter in target_chapters:
        if chapter not in available_chapters:
            print(f"Warning: Chapter {chapter} not found in {part}, skipping.")
            continue
            
        print(f"Processing {part.title()} Chapter {chapter}...")
        
        # Read chapter summaries
        summaries = read_chapter_summaries(part, chapter)
        if not summaries:
            print(f"Warning: No summaries found for {part} chapter {chapter}")
            continue
        
        # Create prompt
        combined_summary = " ".join(summaries)
        prompt = create_illustration_prompt(part, chapter, combined_summary, characters)
        
        # Find next available counter
        counter = 1
        while True:
            test_filename = os.path.join(part, f"{chapter:02d}-{counter}.jpg")
            if not os.path.exists(test_filename):
                break
            counter += 1
        
        # Skip if not append mode and files already exist
        if not append and counter > 1:
            print(f"  Skipping {part.title()} Chapter {chapter} (already exists, use --append to add more)")
            continue
        
        output_filename = os.path.join(part, f"{chapter:02d}-{counter}.jpg")
        
        success = generate_single_image(prompt, reference_image, output_filename)
        
        if success:
            total_generated += 1
    
    return total_generated

def generate_chapter_illustrations(reference_image_path, parts=None, chapters=None, append=False, title_file=None, characters=None):
    """Generate illustrations for specified chapters"""
    
    # Load reference image
    try:
        reference_image = Image.open(reference_image_path)
        print(f"Loaded reference image: {reference_image_path}")
    except FileNotFoundError:
        print(f"Error: Reference image {reference_image_path} not found.")
        return False

    total_generated = 0
    
    if title_file:
        # For title file mode, generate a single image without part/chapter structure
        with open(title_file, 'r', encoding='utf-8') as f:
            title = f.read().strip()
        prompt = create_illustration_prompt(parts[0], None, title, characters)
        
        # Use filename without extension as prefix
        title_prefix = os.path.splitext(os.path.basename(title_file))[0]
        
        # Find next available counter for title-based images
        counter = 1
        while True:
            test_filename = f"{title_prefix}-{counter}.jpg"
            if not os.path.exists(test_filename):
                break
            counter += 1
        
        # Skip if not append mode and files already exist
        if not append and counter > 1:
            print(f"Skipping {title_prefix} image (already exists, use --append to add more)")
            return True
        
        output_filename = test_filename
        
        success = generate_single_image(prompt, reference_image, output_filename)
        
        if success:
            total_generated = 1
    else:
        # Normal mode: process parts and chapters
        if parts is None:
            parts = ["inferno", "purgatorio", "paradiso"]
        
        for part in parts:
            total_generated += process_part(part, chapters, reference_image, append, characters)
    
    print(f"\nGeneration complete! Created {total_generated} illustrations.")
    return True

def main():
    parser = argparse.ArgumentParser(description="Generate illustrations for Dante's Divine Comedy chapters")
    parser.add_argument("reference_image", help="Reference image file path (dante.jpg)")
    parser.add_argument("-p", "--parts", nargs="+", choices=["inferno", "purgatorio", "paradiso"], 
                       help="Specific parts to process (default: all)")
    parser.add_argument("-c", "--chapters", nargs="+", type=int, 
                       help="Specific chapters to process (default: all)")
    parser.add_argument("--append", action="store_true",
                       help="Add new images even if files already exist (creates sequential numbered files)")
    parser.add_argument("--title", type=str,
                       help="Use prompt from specified file instead of chapter summaries")
    parser.add_argument("--characters", type=str,
                       help="Comma-separated list of characters to include (default: Dante,Virgil)")
    
    args = parser.parse_args()
    
    # Parse characters if provided
    characters = None
    if args.characters:
        characters = [char.strip() for char in args.characters.split(',')]
    
    generate_chapter_illustrations(
        reference_image_path=args.reference_image,
        parts=args.parts,
        chapters=args.chapters,
        append=args.append,
        title_file=args.title,
        characters=characters
    )

if __name__ == "__main__":
    main()
