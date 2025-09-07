#!/usr/bin/env python3
"""
Script to check and compare line counts of Dante's Divine Comedy segments
between Italian source and English/Japanese translations.
"""

import json
from collections import defaultdict
from pathlib import Path

def load_segment_data(jsonl_file):
    """Load segment data from JSONL file."""
    segments = []
    try:
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    segments.append(json.loads(line))
    except FileNotFoundError:
        print(f"Warning: File {jsonl_file} not found")
        return []
    except Exception as e:
        print(f"Error reading {jsonl_file}: {e}")
        return []
    return segments

def get_italian_segment_lines(it_segments, part, chapter, segment):
    """Get line count for Italian segment from boundaries."""
    for seg in it_segments:
        if (seg.get('chapter') == chapter and 
            seg.get('filename') == f"{chapter:02d}.txt"):
            
            boundaries = seg.get('response', {}).get('segment_boundaries', [])
            if segment <= len(boundaries):
                if segment == 1:
                    start_line = 1
                else:
                    start_line = boundaries[segment-2]['line_number']
                
                if segment <= len(boundaries):
                    end_line = boundaries[segment-1]['line_number'] - 1
                else:
                    end_line = seg.get('response', {}).get('total_lines', 0)
                
                return end_line - start_line + 1
    return None

def count_translation_lines(translation_text):
    """Count lines in translation text."""
    if not translation_text:
        return 0
    return len(translation_text.strip().split('\n'))

def count_lines_from_txt(part, chapter):
    """Count lines from original txt file."""
    try:
        txt_file = Path('it') / part / f"{chapter:02d}.txt"
        with open(txt_file, 'r', encoding='utf-8') as f:
            return sum(1 for _ in f)
    except Exception:
        return None

def main():
    """Main function to compare segment line counts."""
    
    # Load Italian segment data
    it_inferno = load_segment_data('it/inferno.jsonl')
    it_purgatorio = load_segment_data('it/purgatorio.jsonl')
    it_paradiso = load_segment_data('it/paradiso.jsonl')
    
    it_data = {
        'inferno': it_inferno,
        'purgatorio': it_purgatorio,
        'paradiso': it_paradiso
    }
    
    # Load translation data
    en_segments = load_segment_data('en.jsonl')
    ja_segments = load_segment_data('ja.jsonl')
    
    # Dictionary to store line counts: {part: {chapter: {segment: {lang: line_count}}}}
    line_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    
    # Process Italian data
    for part, segments in it_data.items():
        for seg in segments:
            chapter = seg.get('chapter')
            if not chapter:
                continue
                
            boundaries = seg.get('boundaries', [])
            
            for segment_num, boundary in enumerate(boundaries, 1):
                start_line = boundary['start_line']
                end_line = boundary['end_line']
                
                it_line_count = end_line - start_line + 1
                line_counts[part][chapter][segment_num]['it'] = it_line_count
    
    # Process translation data
    for segments, lang in [(en_segments, 'en'), (ja_segments, 'ja')]:
        for seg in segments:
            part = seg.get('part')
            chapter = seg.get('chapter')
            segment = seg.get('segment')
            translation = seg.get('response', {}).get('translation', '')
            
            if part and chapter and segment and translation:
                trans_line_count = count_translation_lines(translation)
                line_counts[part][chapter][segment][lang] = trans_line_count
                
                # Add Italian line count from txt file for missing cantos
                if 'it' not in line_counts[part][chapter][segment]:
                    if segment == 1:  # Only for single-segment cantos
                        it_line_count = count_lines_from_txt(part, chapter)
                        if it_line_count is not None:
                            line_counts[part][chapter][segment]['it'] = it_line_count
    
    # Check for discrepancies
    print("Segment Line Count Comparison Report")
    print("=" * 60)
    print()
    
    discrepancies_found = False
    total_segments = 0
    matching_segments = 0
    
    for part in ['inferno', 'purgatorio', 'paradiso']:
        print(f"Part: {part.upper()}")
        print("-" * 40)
        
        part_discrepancies = False
        part_segments = 0
        part_matching = 0
        
        for chapter in sorted(line_counts[part].keys()):
            
            for segment in sorted(line_counts[part][chapter].keys()):
                segment_counts = line_counts[part][chapter][segment]
                total_segments += 1
                part_segments += 1
                
                # Check if all languages have the same line count
                counts = list(segment_counts.values())
                if len(set(counts)) > 1:
                    part_discrepancies = True
                    discrepancies_found = True
                    
                    print(f"  Canto {chapter:>2}, Segment {segment}: ", end="")
                    for lang in ['it', 'en', 'ja']:
                        count = segment_counts.get(lang, 'MISSING')
                        print(f"{lang}:{count:>3} ", end="")
                    print(" ← MISMATCH")
                else:
                    matching_segments += 1
                    part_matching += 1
        
        if not part_discrepancies:
            print(f"  All segments have matching line counts")
        else:
            print(f"  Matching segments: {part_matching}/{part_segments}")
        
        print()
    
    # Summary statistics
    print("Summary Statistics")
    print("=" * 60)
    print(f"Total segments checked: {total_segments}")
    print(f"Segments with matching line counts: {matching_segments}")
    print(f"Segments with discrepancies: {total_segments - matching_segments}")
    print()
    
    # Language coverage
    en_count = len(en_segments)
    ja_count = len(ja_segments)
    it_total = sum(len(segs) for segs in it_data.values()) if it_data else 0
    
    print("Translation Coverage:")
    print(f"  Italian segments: {it_total}")
    print(f"  English segments: {en_count}")
    print(f"  Japanese segments: {ja_count}")
    print()
    
    if not discrepancies_found:
        print("✓ All segments have matching line counts!")
    else:
        print(f"✗ Line count discrepancies found in {total_segments - matching_segments} segments")
    
    return 0 if not discrepancies_found else 1

if __name__ == "__main__":
    exit(main())
