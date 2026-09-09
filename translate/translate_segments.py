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
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from llm7shi.compat import generate_with_schema

from common.source import chapter_blocks
from llm7shi import create_json_descriptions_prompt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

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

def resolve_part_order(run_parts: List[str], existing_translations: Dict[tuple, Dict]) -> Dict[str, float]:
    """Build the part -> story-position map used to keep the output file sorted.

    Covers both this run's parts and any parts already present in the output file but
    not passed this run (e.g. resuming inferno only while the file also holds
    purgatorio records). The file is maintained in story order, so the first-appearance
    order of its parts is authoritative for them; parts shared with the run anchor the
    two orders together. File-only parts slot next to their neighboring run parts with
    fractional positions, or before all run parts when they share none.
    """
    order: Dict[str, float] = {part: i for i, part in enumerate(run_parts)}

    if all(key[0] in order for key in existing_translations):
        return order

    # Group the file-only parts by the run part that follows them in the file.
    groups = []  # (position of the following run part, file-only parts preceding it)
    current: List[str] = []
    last_run_part = None
    for key in existing_translations:
        part = key[0]
        if part in order:
            if part != last_run_part:
                groups.append((order[part], current))
                current = []
                last_run_part = part
        elif not current or current[-1] != part:
            current.append(part)
    trailing = current

    for anchor, parts in groups:
        n = len(parts)
        for i, part in enumerate(parts):
            order[part] = anchor - (n - i) / (n + 1)

    n = len(trailing)
    if groups:
        base = groups[-1][0]
        for i, part in enumerate(trailing):
            order[part] = base + (i + 1) / (n + 1)
    else:
        for i, part in enumerate(trailing):
            order[part] = i - n

    return order

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
    maps each part name (including parts that appear only in the output file, see
    resolve_part_order) to its position in story order. Appending is safe (keeps the
    file in story order) only when this record is the new last one in that order;
    otherwise the file must be rewritten in full so it stays sorted.
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

def main():
    parser = argparse.ArgumentParser(description='Translate text segments with proper noun consistency and story context')
    parser.add_argument('parts', nargs='+', help='Canticles to translate (inferno, purgatorio, paradiso)')
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
    parser.add_argument('-n', '--dry-run', action='store_true',
                       help='Show which segments would be translated without calling the LLM')

    args = parser.parse_args()
    
    # Load proper nouns dictionary
    proper_nouns_dict = load_proper_nouns_dictionary(args.proper_nouns, args.from_lang, args.to_lang)
    
    # Load existing translations for resume capability
    existing_translations = load_existing_translations(args.output)
    
    # Process each canticle
    all_data = []
    for part in args.parts:
        segmentation_file = os.path.join(SCRIPT_DIR, "segments", f"{part}.jsonl")
        
        print(f"Loading {part} from dante-corpus using {segmentation_file}")
        
        try:
            all_data.append((part, chapter_blocks(segmentation_file, part)))
        except (FileNotFoundError, KeyError) as e:
            print(f"Warning: {e}")
            continue
    
    if not all_data:
        print("No valid canticles found.")
        return 1

    # Story order for each part, covering parts already in the output file too, used
    # to keep the output JSONL sorted on save
    run_parts = [part for part, _ in all_data]
    part_order = resolve_part_order(run_parts, existing_translations)
    outside = list(dict.fromkeys(k[0] for k in existing_translations if k[0] not in run_parts))
    if outside:
        print(f"Note: {args.output} also contains {', '.join(outside)} records outside this run; they are preserved.")
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
        chapters = data["chapters"]

        print(f"\nProcessing directory: {directory_name}")
        print(f"Title: {title}")
        print(f"Starting translation: {args.from_lang} -> {args.to_lang}")
        print("=" * 60)

        for chapter_num, segments in enumerate(chapters, 1):
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

            if args.dry_run:
                missing = [seg_num for seg_num in range(1, len(segments) + 1)
                           if (directory_name, chapter_num, seg_num) not in existing_translations]
                missing_str = ", ".join(str(n) for n in missing)
                print(f"Chapter {chapter_num:2d}: {len(missing)}/{len(segments)} segments would be translated (segments: {missing_str})")
                translations_done += len(missing)
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

    if args.dry_run:
        print(f"\nDry run: {translations_done} segment(s) would be translated.")
        return 0

    print(f"\nAll translations completed!")
    print(f"Output saved to: {args.output}")
    print(f"Proper nouns dictionary loaded: {len(proper_nouns_dict)} entries")

    return 0

if __name__ == "__main__":
    exit(main())
