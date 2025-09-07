import os
import json
import re
import argparse
import glob
from typing import List
from pydantic import BaseModel, Field
from llm7shi.compat import generate_with_schema
from llm7shi import create_json_descriptions_prompt

class SegmentBoundary(BaseModel):
    reasoning: str = Field(description="Story summary and reason for segmenting at this position")
    line_number: int = Field(description="Line number (relative line number within chapter)")

class ChapterSegmentation(BaseModel):
    reasoning: str = Field(description="Overall story summary and segmentation strategy explanation")
    chapter_number: int = Field(description="Chapter number")
    total_lines: int = Field(description="Total content lines in chapter")
    segment_boundaries: List[SegmentBoundary] = Field(description="List of segment boundaries")

def extract_chapter_content(filename):
    """Extract content from a single chapter file (excluding empty lines)"""
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    content_lines = []
    line_mapping = {}  # content line number -> original line number
    content_line_num = 0
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if line_stripped:  # exclude empty lines
            content_line_num += 1
            content_lines.append(line_stripped)
            line_mapping[content_line_num] = i + 1
    
    return content_lines, line_mapping

def save_segmentation_to_jsonl(chapter_num, result, content_lines, line_mapping, output_file, filename):
    """Convert chapter-relative line numbers to file-global line numbers and save in JSONL format"""
    if not (result and 'segment_boundaries' in result and result['segment_boundaries']):
        return
    
    boundaries = []
    segment_boundaries = [1] + [b['line_number'] for b in result['segment_boundaries']] + [len(content_lines) + 1]
    segment_boundaries = sorted(list(set(segment_boundaries)))
    
    for j in range(len(segment_boundaries) - 1):
        segment_start_relative = segment_boundaries[j]
        segment_end_relative = segment_boundaries[j + 1] - 1
        
        if segment_start_relative <= len(content_lines):
            # Convert to file line numbers using line_mapping
            segment_start_global = line_mapping.get(segment_start_relative, 0)
            segment_end_global = line_mapping.get(segment_end_relative, 0)
            
            boundaries.append({
                "start_line": segment_start_global,
                "end_line": segment_end_global
            })
    
    # Create JSONL record
    record = {
        "chapter": chapter_num,
        "filename": os.path.basename(filename),
        "boundaries": boundaries,
        "response": result
    }
    
    # Append to JSONL file
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

def segment_chapter(chapter_num, content_lines, model, threshold, line_mapping, output_file, filename, show_params):
    """Segment chapter using LLM"""
    
    if len(content_lines) < threshold:
        return None  # don't split chapters below threshold
    
    # prepare chapter content with line numbers
    numbered_content = []
    for i, line in enumerate(content_lines, 1):
        numbered_content.append(f"{i:3d}: {line}")
    
    content_text = "\n".join(["[Chapter Content]", *numbered_content])
    
    prompt = f"""Please analyze the Italian text above from Chapter {chapter_num} and divide it into 2-4 segments based on meaningful story units.

[Task Instructions]
1. First, provide an overall story summary of what happens in this chapter
2. Identify natural breaking points in the narrative flow
3. For each segment boundary, explain what story events occur before and after the break
4. Focus on story progression: character development, plot events, dialogue shifts, scene changes

[Segmentation Guidelines]
- Each segment should be approximately 10-30 lines
- Split at natural narrative breaks: scene changes, character focus shifts, plot developments
- Do not split in the middle of conversations or dramatic moments
- Create a minimum of 2 and maximum of 4 segments
- Prioritize story coherence over line count

[Output Format]
- reasoning: Provide a comprehensive story summary of the entire chapter
- segment_boundaries: For each boundary, explain the story transition that occurs at that point
- line_number: Starting line number of each new segment

Specify segment boundaries as the starting line numbers of new segments.
Example: To split at line 15, specify 15 as boundary (line 15 becomes start of new segment)"""
    
    json_descriptions = create_json_descriptions_prompt(ChapterSegmentation)
    
    try:
        result = generate_with_schema(
            [content_text, prompt, json_descriptions],
            schema=ChapterSegmentation,
            model=model,
            show_params=show_params,
        )
        
        # Extract JSON from result.text and parse it
        if result and hasattr(result, 'text'):
            try:
                segmentation_data = json.loads(result.text)
                # Save segmentation result to file  
                if output_file:
                    save_segmentation_to_jsonl(chapter_num, segmentation_data, content_lines, line_mapping, output_file, filename)
                return segmentation_data
            except json.JSONDecodeError as e:
                print(f"  DEBUG: Failed to parse JSON: {e}")
                return None
        else:
            print(f"  DEBUG: No result.text found")
            return None
    except Exception as e:
        print(f"Error segmenting chapter {chapter_num}: {e}")
        return None

def create_translation_chunks(directory, model, output_file, limit=None):
    """Analyze all chapters from individual files and create translation chunks"""
    
    # Get all .txt files in the directory and sort them
    chapter_files = sorted(glob.glob(os.path.join(directory, '*.txt')))
    
    if not chapter_files:
        raise FileNotFoundError(f"No .txt files found in directory '{directory}'")
    
    translation_chunks = []
    threshold = 25
    
    # Apply limit if specified
    if limit:
        chapter_files = chapter_files[:limit]
        print(f"Starting translation chunk creation (threshold: {threshold} lines, limit: {limit} chapters)")
    else:
        print(f"Starting translation chunk creation (threshold: {threshold} lines)")
    print("=" * 60)
    
    for i, chapter_file in enumerate(chapter_files, 1):
        chapter_num = int(os.path.basename(chapter_file).replace('.txt', ''))
        
        # Extract content from single chapter file
        chunk_content, line_mapping = extract_chapter_content(chapter_file)
        content_lines = len(chunk_content)
        
        print(f"Chapter {chapter_num:2d}: {content_lines:2d} lines ", end="")
        
        if content_lines < threshold:
            # add as-is as translation chunk
            translation_chunks.append({
                'type': 'whole_chapter',
                'chapter': chapter_num,
                'filename': os.path.basename(chapter_file),
                'content': chunk_content,
                'lines': content_lines,
                'source_lines': f"1-{len(chunk_content)}"
            })
            print("→ translate as-is")
        else:
            # segment using LLM
            print("→ segmenting...", end="")
            
            segmentation = segment_chapter(chapter_num, chunk_content, model, threshold, line_mapping, output_file, chapter_file, bool(limit))
            
            if segmentation and 'segment_boundaries' in segmentation and segmentation['segment_boundaries']:
                # split into segments
                boundaries = [1] + [b['line_number'] for b in segmentation['segment_boundaries']] + [len(chunk_content) + 1]
                boundaries = sorted(list(set(boundaries)))  # remove duplicates and sort
                
                for j in range(len(boundaries) - 1):
                    segment_start = boundaries[j]
                    segment_end = boundaries[j + 1] - 1
                    
                    if segment_start <= len(chunk_content):
                        segment_content = chunk_content[segment_start-1:segment_end]
                        original_start = line_mapping.get(segment_start, 1)
                        original_end = line_mapping.get(segment_end, len(chunk_content))
                        
                        translation_chunks.append({
                            'type': 'chapter_segment',
                            'chapter': chapter_num,
                            'filename': os.path.basename(chapter_file),
                            'segment': j + 1,
                            'content': segment_content,
                            'lines': len(segment_content),
                            'source_lines': f"{original_start}-{original_end}"
                        })
                
                print(f" completed ({len(boundaries)-1} segments)")
            else:
                # fallback: split in half when segmentation fails
                mid = len(chunk_content) // 2
                
                translation_chunks.append({
                    'type': 'chapter_half',
                    'chapter': chapter_num,
                    'filename': os.path.basename(chapter_file),
                    'segment': 1,
                    'content': chunk_content[:mid],
                    'lines': mid,
                    'source_lines': f"1-{mid}"
                })
                
                translation_chunks.append({
                    'type': 'chapter_half', 
                    'chapter': chapter_num,
                    'filename': os.path.basename(chapter_file),
                    'segment': 2,
                    'content': chunk_content[mid:],
                    'lines': len(chunk_content) - mid,
                    'source_lines': f"{mid+1}-{len(chunk_content)}"
                })
                print(" failed → split in 2")
    
    return translation_chunks

def main():
    parser = argparse.ArgumentParser(description='Segment Italian chapters for translation using LLM')
    parser.add_argument('-m', '--model', required=True, 
                       help='LLM model to use for segmentation (e.g., openai:gpt-4o-mini, anthropic:claude-3-haiku-20240307)')
    parser.add_argument('-o', '--output', required=True,
                       help='Output JSONL file to save segmentation results')
    parser.add_argument('--limit', type=int, 
                       help='Limit number of chapters to process (for debugging)')
    parser.add_argument('directory', nargs='?', default='.',
                       help='Directory containing chapter .txt files (default: current directory)')
    
    args = parser.parse_args()
    
    try:
        chunks = create_translation_chunks(args.directory, args.model, args.output, args.limit)
        
        print(f"\nTranslation preparation completed!")
        print(f"Total chunks: {len(chunks)}")
        print(f"Average lines: {sum(c['lines'] for c in chunks) / len(chunks):.1f} lines")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
