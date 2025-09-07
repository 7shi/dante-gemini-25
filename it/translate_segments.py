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
    translation_result: Dict
) -> None:
    """Save translation result to JSONL file"""
    record = {
        "part": part,
        "chapter": chapter,
        "segment": segment,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "response": translation_result
    }
    
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

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
                       help='LLM model to use (e.g., openai:gpt-4o-mini, anthropic:claude-3-haiku-20240307)')
    parser.add_argument('-o', '--output', required=True,
                       help='Output JSONL file for translation results')
    parser.add_argument('--proper-nouns', default='proper_nouns/all.tsv',
                       help='Proper nouns dictionary TSV file (default: proper_nouns/all.tsv)')
    parser.add_argument('--limit', type=int,
                       help='Limit number of chapters to process (for debugging)')
    
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
    
    # Initialize context tracking - load summaries from all previously completed chapters across all directories
    previous_summaries = []
    
    # Load existing summaries from all completed segments across all directories
    for directory_name, data in all_data:
        chapter_blocks = data["chapters"]
        total_chapters_in_file = len(chapter_blocks)
        
        for chapter_num in range(1, total_chapters_in_file + 1):
            if chapter_num <= len(chapter_blocks):
                chapter_segments = chapter_blocks[chapter_num - 1]
                chapter_complete = all(
                    (directory_name, chapter_num, seg_num) in existing_translations
                    for seg_num in range(1, len(chapter_segments) + 1)
                )
                if chapter_complete:
                    # Load all summaries from this completed chapter
                    for seg_num in range(1, len(chapter_segments) + 1):
                        existing = existing_translations.get((directory_name, chapter_num, seg_num), {})
                        if existing.get("summary"):
                            previous_summaries.append(existing["summary"])
                        elif existing.get("response", {}).get("summary"):
                            previous_summaries.append(existing["response"]["summary"])
    
    # Apply global chapter limit if specified - find next incomplete chapters across all directories
    global_chapters_to_process = []
    global_chapters_processed = 0
    
    if args.limit:
        # Collect incomplete chapters across all directories until limit is reached
        for directory_name, data in all_data:
            chapter_blocks = data["chapters"]
            for chapter_num, segments in enumerate(chapter_blocks, 1):
                # Check if this chapter is already complete
                chapter_complete = all(
                    (directory_name, chapter_num, seg_num) in existing_translations
                    for seg_num in range(1, len(segments) + 1)
                )
                if not chapter_complete:
                    global_chapters_to_process.append((directory_name, data, chapter_num, segments))
                    global_chapters_processed += 1
                    if global_chapters_processed >= args.limit:
                        break
            if global_chapters_processed >= args.limit:
                break
        
        print(f"Global limit: Processing {len(global_chapters_to_process)} incomplete chapters (limit: {args.limit})")
    else:
        # Collect all chapters from all directories
        for directory_name, data in all_data:
            chapter_blocks = data["chapters"]
            for chapter_num, segments in enumerate(chapter_blocks, 1):
                global_chapters_to_process.append((directory_name, data, chapter_num, segments))
    
    # Group chapters by directory for organized processing
    chapters_by_directory = {}
    for directory_name, data, chapter_num, segments in global_chapters_to_process:
        if directory_name not in chapters_by_directory:
            chapters_by_directory[directory_name] = {'data': data, 'chapters': []}
        chapters_by_directory[directory_name]['chapters'].append((chapter_num, segments))
    
    # Process directories with their selected chapters
    for directory_name, dir_info in chapters_by_directory.items():
        title = dir_info['data']["title"]
        chapter_blocks_to_process = dir_info['chapters']
        all_chapter_blocks = dir_info['data']["chapters"]
        
        print(f"\nProcessing directory: {directory_name}")
        print(f"Title: {title}")
        print(f"Starting translation: {args.from_lang} -> {args.to_lang}")
        print(f"Chapters to process: {len(chapter_blocks_to_process)}")
        print("=" * 60)
        
        # Store total chapters count in this directory
        total_chapters_in_file = len(all_chapter_blocks)
        
        total_segments = sum(len(segments) for _, segments in chapter_blocks_to_process)
        processed_segments = 0
        completed_chapters = set()  # Track chapters that have been fully translated
        
        for chapter_num, segments in chapter_blocks_to_process:
            print(f"Chapter {chapter_num:2d}: {len(segments)} segments")
            
            for segment_num, segment_text in enumerate(segments, 1):
                processed_segments += 1
                segment_key = (directory_name, chapter_num, segment_num)
                
                # Check if already processed
                if segment_key in existing_translations:
                    print(f"  Segment {segment_num} → skipped (already processed)")
                    # Load existing summary for context
                    existing = existing_translations[segment_key]
                    # Check both old format (summary field) and new format (response.summary)
                    if existing.get("summary"):
                        previous_summaries.append(existing["summary"])
                    elif existing.get("response", {}).get("summary"):
                        previous_summaries.append(existing["response"]["summary"])
                    continue
                
                print(f"  Segment {segment_num} → translating...\n")
                
                # Translate segment
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
                    # Update context
                    if translation_result.get("summary"):
                        previous_summaries.append(translation_result["summary"])
                    
                    # Save result
                    save_translation_result(
                        args.output,
                        directory_name,
                        chapter_num,
                        segment_num,
                        args.from_lang,
                        args.to_lang,
                        translation_result
                    )
                    
                    # Update existing_translations for chapter completion tracking
                    existing_translations[segment_key] = translation_result
                    
                    print(" completed")
                else:
                    print(" failed")
                
                # Progress indicator
                print(f"  Progress: {processed_segments}/{total_segments} segments")
            
            # Check if this chapter is fully completed (all segments translated)
            chapter_segments_completed = all(
                (directory_name, chapter_num, seg_num) in existing_translations
                for seg_num in range(1, len(segments) + 1)
            )
            if chapter_segments_completed:
                completed_chapters.add(chapter_num)
        
        # Count total completed chapters (including previously translated ones)
        all_completed_chapters = set()
        for chapter_num in range(1, total_chapters_in_file + 1):
            if chapter_num <= len(all_chapter_blocks):
                chapter_length = len(all_chapter_blocks[chapter_num - 1])
                if all((directory_name, chapter_num, seg_num) in existing_translations 
                        for seg_num in range(1, chapter_length + 1)):
                    all_completed_chapters.add(chapter_num)
        
        # Add currently completed chapters
        all_completed_chapters.update(completed_chapters)
        
    
    print(f"\nAll translations completed!")
    print(f"Output saved to: {args.output}")
    print(f"Proper nouns dictionary loaded: {len(proper_nouns_dict)} entries")
    if args.limit:
        print(f"Global chapter limit applied: {args.limit} chapters processed")
    
    return 0

if __name__ == "__main__":
    exit(main())
