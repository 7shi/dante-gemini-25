import os
import re
import json
import argparse
import time
from collections import defaultdict
from typing import Dict, List, Tuple
from pydantic import BaseModel, Field
from llm7shi.compat import generate_with_schema
from llm7shi import create_json_descriptions_prompt

class CantoSummary(BaseModel):
    """One-line summary of a complete canto"""
    summary: str = Field(
        description="One-sentence summary of the entire canto in the same language as the segment summaries"
    )

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

def load_segment_summaries(input_file: str) -> Dict[str, Dict[int, List[Tuple[int, str]]]]:
    """Load segment summaries from JSONL file grouped by part and chapter"""
    summaries_by_part = defaultdict(lambda: defaultdict(list))
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            entry = json.loads(line)
            part = entry['part']
            chapter = entry['chapter']
            segment = entry['segment']
            summary = entry['response']['summary']
            
            summaries_by_part[part][chapter].append((segment, summary))
    
    return summaries_by_part

def summarize_canto(part: str, chapter: int, summaries: List[str], model: str, show_params: bool) -> Dict:
    """Summarize a complete canto into one line from its segment summaries"""
    
    summary_list = "\n".join(f"- {s}" for s in summaries)
    
    prompt = f"""Please write a one-line summary of {part.title()} Canto {chapter} based on the segment summaries below.

[{part.title()} Canto {chapter} Segment Summaries]
{summary_list}

[Summary Instructions]
1. Write exactly one sentence that captures the main events of the entire canto
2. Keep it concise (under 40 words)
3. Use the same language as the segment summaries
4. Focus on the most important narrative events and characters
5. Write in a clear narrative style using past tense"""
    
    json_descriptions = create_json_descriptions_prompt(CantoSummary)
    return generate(
        [prompt, json_descriptions],
        schema=CantoSummary,
        model=model,
        show_params=show_params,
    )

def load_existing_summaries(markdown_dir: str, parts) -> Dict[tuple, str]:
    """Load existing one-line summaries from markdown files to support resume functionality"""
    existing = {}
    
    for part in parts:
        markdown_file = os.path.join(markdown_dir, f"{part}-1.md")
        if not os.path.exists(markdown_file):
            continue
        
        with open(markdown_file, 'r', encoding='utf-8') as f:
            for line in f:
                match = re.match(r'^(\d+)\. (.*)$', line.strip())
                if match:
                    existing[(part, int(match.group(1)))] = match.group(2)
    
    return existing

def write_markdown(part: str, chapter_summaries: Dict[int, str], markdown_dir: str) -> None:
    """Write markdown file with one-line summaries for a part"""
    
    if not chapter_summaries:
        return
    
    os.makedirs(markdown_dir, exist_ok=True)
    markdown_file = os.path.join(markdown_dir, f"{part}-1.md")
    with open(markdown_file, 'w', encoding='utf-8') as f:
        for chapter in sorted(chapter_summaries.keys()):
            summary = " ".join(chapter_summaries[chapter].split())
            print(f"{chapter}. {summary}", file=f)
    
    print(f"Created/Updated: {markdown_file}")

def main():
    parser = argparse.ArgumentParser(description='Generate one-line summaries for each canto from segment summaries')
    parser.add_argument('input_file', help='Input JSONL file containing segment translations with summaries')
    parser.add_argument('-m', '--model', required=True,
                       help='LLM model to use (e.g., gemini-2.5-pro, openai:gpt-5.6-luna)')
    parser.add_argument('-o', '--output-dir', default=None,
                       help='Output directory for markdown files (default: directory named after input file stem)')
    parser.add_argument('--limit', type=int,
                       help='Limit number of chapters to process (for debugging)')
    
    args = parser.parse_args()
    
    # Determine markdown output directory
    if args.output_dir:
        markdown_dir = args.output_dir
    else:
        stem = os.path.splitext(os.path.basename(args.input_file))[0]
        markdown_dir = stem
    
    # Load segment summaries grouped by part and chapter
    summaries_by_part = load_segment_summaries(args.input_file)
    
    # Load existing summaries from markdown files for resume capability
    existing_summaries = load_existing_summaries(markdown_dir, summaries_by_part.keys())
    
    # Merge existing summaries into current results
    chapter_summaries_by_part = defaultdict(dict)
    for (part, chapter), summary in existing_summaries.items():
        if part in summaries_by_part and chapter in summaries_by_part[part]:
            chapter_summaries_by_part[part][chapter] = summary
    
    # Collect incomplete chapters in processing order
    chapters_to_process = []
    for part, chapters in summaries_by_part.items():
        for chapter, segments in chapters.items():
            if chapter in chapter_summaries_by_part[part]:
                print(f"{part} Canto {chapter:2d} → skipped (already summarized)")
                continue
            chapters_to_process.append((part, chapter, segments))
    
    if args.limit:
        chapters_to_process = chapters_to_process[:args.limit]
        print(f"Limit: Processing {len(chapters_to_process)} incomplete chapters (limit: {args.limit})")
    
    print(f"Chapters to process: {len(chapters_to_process)}")
    print("=" * 60)
    
    for part, chapter, segments in chapters_to_process:
        segments.sort(key=lambda x: x[0])
        summaries = [" ".join(s.split()) for _, s in segments]
        
        print(f"{part} Canto {chapter:2d} ({len(summaries)} segments) → summarizing...")
        
        summary_result = summarize_canto(part, chapter, summaries, args.model, bool(args.limit))
        
        if summary_result and summary_result.get("summary"):
            chapter_summaries_by_part[part][chapter] = summary_result["summary"]
            write_markdown(part, chapter_summaries_by_part[part], markdown_dir)
            print(" completed")
        else:
            print(" failed")
    
    print(f"\nAll summaries completed!")
    print(f"Output saved to: {markdown_dir}/")
    
    return 0

if __name__ == "__main__":
    exit(main())
