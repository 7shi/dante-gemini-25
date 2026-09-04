import json
import os
import argparse
from collections import defaultdict

def convert_dante_jsonl(input_file, output_dir='.'):
    data_by_part_chapter = defaultdict(lambda: defaultdict(list))
    summaries_by_part_chapter = defaultdict(lambda: defaultdict(list))
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            entry = json.loads(line)
            part = entry['part']
            chapter = entry['chapter']
            segment = entry['segment']
            translation = entry['response']['translation']
            summary = entry['response']['summary']
            
            data_by_part_chapter[part][chapter].append((segment, translation))
            summaries_by_part_chapter[part][chapter].append((segment, summary))
    
    for part, chapters in data_by_part_chapter.items():
        part_dir = os.path.join(output_dir, part)
        os.makedirs(part_dir, exist_ok=True)
        
        # Create individual text files with translations
        for chapter, segments in chapters.items():
            segments.sort(key=lambda x: x[0])
            
            output_file = os.path.join(part_dir, f"{chapter:02d}.txt")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                for segment_num, translation in segments:
                    print(translation.strip(), file=f)
            
            print(f"Created: {output_file} ({len(segments)} segments)")
        
        # Create markdown file with summaries
        markdown_file = os.path.join(output_dir, f"{part}.md")
        with open(markdown_file, 'w', encoding='utf-8') as f:
            for i, chapter in enumerate(sorted(chapters.keys())):
                if i:
                    print("", file=f)
                print(f"## Canto {chapter}", file=f)
                
                chapter_summaries = summaries_by_part_chapter[part][chapter]
                chapter_summaries.sort(key=lambda x: x[0])
                
                for segment_num, summary in chapter_summaries:
                    print("", file=f)
                    print(summary.replace("\n", " ").strip(), file=f)
        
        print(f"Created: {markdown_file}")

def main():
    parser = argparse.ArgumentParser(description='Convert Dante JSONL file to structured text files')
    parser.add_argument('input_file', help='Input JSONL file path')
    parser.add_argument('--output-dir', default='.', help='Output directory (default: current directory)')
    
    args = parser.parse_args()
    
    convert_dante_jsonl(args.input_file, args.output_dir)
    print("Conversion completed!")

if __name__ == "__main__":
    main()
