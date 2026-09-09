import json
import os
import re
import argparse
from collections import defaultdict

def load_jsonl(input_file):
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

    return data_by_part_chapter, summaries_by_part_chapter

def parse_segment_arg(value):
    m = re.fullmatch(r"(\w+):(\d+):(\d+)", value.strip())
    if not m:
        raise argparse.ArgumentTypeError(
            "expected part:chapter:segment, e.g. inferno:1:1")
    part = m.group(1)
    return part, int(m.group(2)), int(m.group(3))

def update_segments(input_file, output_dir, segment_args):
    data_by_part_chapter, _ = load_jsonl(input_file)

    targets = defaultdict(set)
    for part, chapter, segment in segment_args:
        targets[(part, chapter)].add(segment)

    for (part, chapter), target_segments in targets.items():
        if part not in data_by_part_chapter or chapter not in data_by_part_chapter[part]:
            raise SystemExit(f"error: no data for {part}:{chapter} in {input_file}")

        segments = sorted(data_by_part_chapter[part][chapter], key=lambda x: x[0])
        known = {segnum for segnum, _ in segments}
        missing = target_segments - known
        if missing:
            raise SystemExit(
                f"error: {part}:{chapter} has no segment(s) "
                f"{sorted(missing)} in {input_file}")

        min_t, max_t = min(target_segments), max(target_segments)

        def line_count(translation):
            return len(translation.strip().split('\n'))

        prefix_len = sum(line_count(t) for n, t in segments if n < min_t)
        suffix_len = sum(line_count(t) for n, t in segments if n > max_t)

        output_file = os.path.join(output_dir, part, f"{chapter:02d}.txt")
        if not os.path.exists(output_file):
            raise SystemExit(f"error: {output_file} does not exist")

        with open(output_file, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()

        total = len(lines)
        old_middle_len = total - prefix_len - suffix_len
        if old_middle_len < 0:
            raise SystemExit(
                f"error: {output_file} line count doesn't match {input_file} "
                f"for the untouched segments of {part}:{chapter} "
                f"(expected at least {prefix_len + suffix_len} lines, got {total})")

        new_middle_lines = []
        for n, t in segments:
            if min_t <= n <= max_t:
                new_middle_lines.extend(t.strip().split('\n'))

        new_lines = lines[:prefix_len] + new_middle_lines + lines[prefix_len + old_middle_len:]

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines) + '\n')

        replaced = sorted(target_segments)
        print(f"Updated: {output_file} (segment(s) {replaced})")

def convert_dante_jsonl(input_file, output_dir='.'):
    data_by_part_chapter, summaries_by_part_chapter = load_jsonl(input_file)

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
    parser.add_argument('-s', '--segment', type=parse_segment_arg, action='append',
                        help='Replace only this segment\'s translation in the existing '
                        '.txt file, leaving the rest of the file untouched (repeatable), '
                        'e.g. inferno:1:1')

    args = parser.parse_args()

    if args.segment:
        update_segments(args.input_file, args.output_dir, args.segment)
    else:
        convert_dante_jsonl(args.input_file, args.output_dir)
        print("Conversion completed!")

if __name__ == "__main__":
    main()
