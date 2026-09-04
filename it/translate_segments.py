"""Translate text segments with proper noun consistency and story context.

Chapters must be generated in story order, front to back, with no gaps: the
"previous story context" fed to each translation call is built by walking
directories/chapters in order and collecting summaries of completed chapters
before the first incomplete one, then accumulating further summaries as the
processing loop advances. If a later chapter is generated (or resumed) while
an earlier one is still missing, or an already-completed chapter is deleted
and left unregenerated out of order, the context will omit, duplicate, or
scramble summaries relative to story order.
"""

import os
import json
import argparse
import time
import glob
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from llm7shi.compat import generate_with_schema
from llm7shi import create_json_descriptions_prompt

class SegmentTranslation(BaseModel):
    """Complete translation result for a text segment"""
    summary: str = Field(
        description="Brief summary of this segment's content in the target language"
    )
    translation_notes: str = Field(
        description="Translation breakdown and notes - explain key translation choices, difficult phrases, cultural adaptations, or linguistic considerations"
    )
    translation: str = Field(
        description="Complete translation of the segment text into the target language"
    )

def load_proper_nouns_dictionary(dict_file: str, source_lang: str = "Italian", target_lang: str = "Japanese") -> Dict[str, str]:
    """Load proper nouns dictionary from TSV file"""
    if not os.path.exists(dict_file):
        return {}
    
    proper_nouns_dict = {}
    with open(dict_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        if not lines:
            return {}
        
        # Parse header line to find column indices
        header = lines[0].strip().split('\t')
        source_col = -1
        target_col = -1
        
        for i, col_name in enumerate(header):
            if col_name.lower() == source_lang.lower():
                source_col = i
            elif col_name.lower() == target_lang.lower():
                target_col = i
        
        if source_col == -1 or target_col == -1:
            print(f"Warning: Could not find columns for {source_lang} or {target_lang} in TSV header")
            return {}
        
        # Parse data lines
        for line in lines[1:]:
            if line.strip():  # Skip empty lines
                parts = line.strip().split('\t')
                if len(parts) > max(source_col, target_col):
                    source_term = parts[source_col].strip()
                    target_term = parts[target_col].strip()
                    if source_term and target_term:  # Only add non-empty entries
                        proper_nouns_dict[source_term] = target_term
    
    return proper_nouns_dict

def create_translation_context(
    proper_nouns_dict: Dict[str, str], 
    previous_summaries: List[str], 
    source_lang: str, 
    target_lang: str
) -> str:
    """Create context string for translation including proper nouns dictionary and story summary"""
    context_parts = []
    
    if proper_nouns_dict:
        context_parts.append(f"[Proper Nouns Dictionary ({source_lang} -> {target_lang})]")
        for source_noun, target_noun in proper_nouns_dict.items():
            context_parts.append(f"{source_noun}: {target_noun}")
        context_parts.append("")
    
    if previous_summaries:
        context_parts.append(f"[Previous Story Context in {target_lang}]")
        context_parts.extend(previous_summaries)
        context_parts.append("")
    
    return "\n".join(context_parts)

def generate(messages, **kwargs):
    """Generate a response from the model based on the provided messages and parameters."""
    for attempt in range(5, 0, -1):
        response = generate_with_schema(messages, **kwargs)
        try:
            text = response.text.strip()
            # Check if response starts with ```json and extract content between backticks
            if text.startswith("```json"):
                start_idx = text.find("```json") + 7  # Skip past ```json
                end_idx = text.find("```", start_idx)
                if end_idx != -1:
                    text = text[start_idx:end_idx].strip()
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
        if attempt > 1:
            for i in range(5, -1, -1):
                print(f"\rRetrying... {i}s ", end="", flush=True)
                time.sleep(1)
            print()

def translate_segment(
    segment_text: str,
    proper_nouns_dict: Dict[str, str],
    previous_summaries: List[str],
    source_lang: str,
    target_lang: str,
    model: str,
    show_params: bool
) -> Optional[Dict]:
    """Translate a single segment with proper noun consistency and story context"""
    
    context = create_translation_context(
        proper_nouns_dict, 
        previous_summaries, 
        source_lang, 
        target_lang
    )
    
    prompt = f"""Please translate the following {source_lang} text segment into {target_lang}.

[{source_lang.title()} Text to Translate]
{segment_text}

[Translation Instructions]
1. Maintain consistency with the proper nouns dictionary above - use the exact same transliterations
2. Consider the story context from previous segments to ensure narrative continuity
3. Prioritize literal translation as much as possible - stay close to the original word order and structure
4. Translate line by line, preserving the original line breaks - each line of the original should correspond to one line in the translation
5. Line correspondence takes priority over grammatical fluency - maintain one-to-one line mapping even if it results in less natural grammar
6. Provide translation notes explaining key choices and cultural context"""
    
    json_descriptions = create_json_descriptions_prompt(SegmentTranslation)
    return generate(
        [context, prompt, json_descriptions],
        schema=SegmentTranslation,
        model=model,
        show_params=show_params,
    )

def load_existing_translations(output_file: str) -> Dict[tuple, Dict]:
    """Load existing translations from output file to support resume functionality"""
    existing = {}
    
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    # Use part, chapter, segment as key for uniqueness across parts
                    key = (data['part'], data['chapter'], data['segment'])
                    existing[key] = data
    
    return existing

def save_translation_result(
    output_file: str,
    part: str,
    chapter: int,
    segment: int,
    source_lang: str,
    target_lang: str,
    translation_result: Dict,
    known_records: Dict[tuple, Dict],
    part_order: Dict[str, int]
) -> None:
    """Save translation result to JSONL file.

    known_records holds every record currently in output_file (as of the start of this
    run, updated as records are added), keyed by (part, chapter, segment). part_order
    maps each part name to its position in story order (the order of the directories
    argument). Appending is safe (keeps the file in story order) only when this record
    is the new last one in that order; otherwise the file must be rewritten in full so
    it stays sorted.
    """
    record = {
        "part": part,
        "chapter": chapter,
        "segment": segment,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "response": translation_result
    }
    key = (part, chapter, segment)
    order_key = (part_order[part], chapter, segment)

    is_new_max = not known_records or order_key > max(
        (part_order[p], c, s) for p, c, s in known_records
    )
    known_records[key] = record

    if is_new_max:
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    else:
        with open(output_file, 'w', encoding='utf-8') as f:
            for k in sorted(known_records, key=lambda k: (part_order[k[0]], k[1], k[2])):
                f.write(json.dumps(known_records[k], ensure_ascii=False) + '\n')

def load_chapter_blocks_from_directory(segmentation_file: str, directory: str) -> Dict:
    """Load chapter blocks from directory-based segmentation data"""
    
    # Load segmentation data
    segmentation_data = {}
    if os.path.exists(segmentation_file):
        with open(segmentation_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    chapter_num = data['chapter']
                    segmentation_data[chapter_num] = data
    
    # Get all .txt files in the directory and sort them
    chapter_files = sorted(glob.glob(os.path.join(directory, '*.txt')))
    
    if not chapter_files:
        raise FileNotFoundError(f"No .txt files found in directory '{directory}'")
    
    chapter_blocks = []
    
    for chapter_file in chapter_files:
        chapter_num = int(os.path.basename(chapter_file).replace('.txt', ''))
        
        # Read chapter content
        with open(chapter_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
        
        # Get segmentation boundaries for this chapter
        if chapter_num in segmentation_data:
            boundaries_data = segmentation_data[chapter_num]['boundaries']
            
            # Create segments based on boundaries
            segments = []
            for boundary in boundaries_data:
                start_line = boundary['start_line'] - 1  # Convert to 0-based index
                end_line = boundary['end_line'] - 1      # Convert to 0-based index
                
                if start_line < len(lines) and end_line < len(lines):
                    segment_lines = lines[start_line:end_line + 1]
                    segment_text = '\n'.join(segment_lines)
                    segments.append(segment_text)
            
            chapter_blocks.append(segments)
        else:
            # No segmentation data, treat entire chapter as one segment
            chapter_text = '\n'.join(lines)
            chapter_blocks.append([chapter_text])
    
    # Extract title from directory name or use default
    title = os.path.basename(directory).title()
    
    return {
        "title": title,
        "chapters": chapter_blocks
    }

def main():
    parser = argparse.ArgumentParser(description='Translate text segments with proper noun consistency and story context')
    parser.add_argument('directories', nargs='+', help='Source directories containing chapter .txt files')
    parser.add_argument('-f', '--from_lang', required=True, 
                       help='Source language (e.g., italian, english, japanese)')
    parser.add_argument('-t', '--to_lang', required=True,
                       help='Target language (e.g., english, japanese, italian)')
    parser.add_argument('-m', '--model', required=True,
                       help='LLM model to use (e.g., gemini-2.5-pro, openai:gpt-5.6-luna)')
    parser.add_argument('-o', '--output', required=True,
                       help='Output JSONL file for translation results')
    parser.add_argument('--proper-nouns', default='proper_nouns/all.tsv',
                       help='Proper nouns dictionary TSV file (default: proper_nouns/all.tsv)')
    parser.add_argument('--limit', type=int,
                       help='Limit number of segment translations to perform this run (for debugging)')
    
    args = parser.parse_args()
    
    # Load proper nouns dictionary
    proper_nouns_dict = load_proper_nouns_dictionary(args.proper_nouns, args.from_lang, args.to_lang)
    
    # Load existing translations for resume capability
    existing_translations = load_existing_translations(args.output)
    
    # Process each directory
    all_data = []
    for directory in args.directories:
        directory_name = os.path.basename(directory)
        segmentation_file = f"{directory_name}.jsonl"
        
        print(f"Loading segments from {directory} using {segmentation_file}")
        
        try:
            data = load_chapter_blocks_from_directory(segmentation_file, directory)
            all_data.append((directory_name, data))
        except FileNotFoundError as e:
            print(f"Warning: {e}")
            continue
    
    if not all_data:
        print("No valid directories found.")
        return 1

    # Story order for each part, used to keep the output JSONL sorted on save
    part_order = {directory_name: idx for idx, (directory_name, _) in enumerate(all_data)}
    known_records = dict(existing_translations)

    # Single pass over every chapter in story order (directories, then chapters within
    # each). existing_translations is the full on-disk state loaded up front, and is
    # updated in place as segments are translated, so it always reflects "what's done so
    # far" for both already-logged and newly-translated segments. previous_summaries is
    # built by walking that same order: a chapter already fully logged contributes its
    # summaries straight from the cache at no cost; a chapter needing translation uses
    # everything accumulated before it as context, then contributes its own summaries as
    # they're produced. --limit caps the number of segment translations (LLM calls) made
    # in this run, not the number of chapters.
    previous_summaries = []
    translations_done = 0

    for directory_name, data in all_data:
        title = data["title"]
        chapter_blocks = data["chapters"]

        print(f"\nProcessing directory: {directory_name}")
        print(f"Title: {title}")
        print(f"Starting translation: {args.from_lang} -> {args.to_lang}")
        print("=" * 60)

        for chapter_num, segments in enumerate(chapter_blocks, 1):
            chapter_complete = all(
                (directory_name, chapter_num, seg_num) in existing_translations
                for seg_num in range(1, len(segments) + 1)
            )
            if chapter_complete:
                for seg_num in range(1, len(segments) + 1):
                    existing = existing_translations[(directory_name, chapter_num, seg_num)]
                    if existing.get("summary"):
                        previous_summaries.append(existing["summary"])
                    elif existing.get("response", {}).get("summary"):
                        previous_summaries.append(existing["response"]["summary"])
                continue

            if args.limit and translations_done >= args.limit:
                print(f"Limit of {args.limit} translations reached, stopping.")
                print(f"\nOutput saved to: {args.output}")
                return 0

            print(f"Chapter {chapter_num:2d}: {len(segments)} segments")

            for segment_num, segment_text in enumerate(segments, 1):
                segment_key = (directory_name, chapter_num, segment_num)

                # Check if already processed
                if segment_key in existing_translations:
                    print(f"  Segment {segment_num} → skipped (already processed)")
                    existing = existing_translations[segment_key]
                    if existing.get("summary"):
                        previous_summaries.append(existing["summary"])
                    elif existing.get("response", {}).get("summary"):
                        previous_summaries.append(existing["response"]["summary"])
                    continue

                if args.limit and translations_done >= args.limit:
                    print(f"Limit of {args.limit} translations reached, stopping.")
                    print(f"\nOutput saved to: {args.output}")
                    return 0

                print(f"  Segment {segment_num} → translating...\n")

                translation_result = translate_segment(
                    segment_text,
                    proper_nouns_dict,
                    previous_summaries,
                    args.from_lang,
                    args.to_lang,
                    args.model,
                    bool(args.limit)
                )

                if translation_result:
                    if translation_result.get("summary"):
                        previous_summaries.append(translation_result["summary"])

                    save_translation_result(
                        args.output,
                        directory_name,
                        chapter_num,
                        segment_num,
                        args.from_lang,
                        args.to_lang,
                        translation_result,
                        known_records,
                        part_order
                    )

                    existing_translations[segment_key] = translation_result
                    translations_done += 1

                    print(" completed")
                else:
                    print(" failed")

    print(f"\nAll translations completed!")
    print(f"Output saved to: {args.output}")
    print(f"Proper nouns dictionary loaded: {len(proper_nouns_dict)} entries")

    return 0

if __name__ == "__main__":
    exit(main())
