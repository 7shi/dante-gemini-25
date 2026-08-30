import json
import time
import argparse
from pydantic import BaseModel, Field
from llm7shi.compat import generate_with_schema
from llm7shi import create_json_descriptions_prompt

class SegmentSummary(BaseModel):
    """One-line summary of a single translated segment"""
    summary: str = Field(
        description="Brief summary of this segment's content, in the same language as the segment text"
    )

def generate(messages, **kwargs):
    """Generate a response from the model based on the provided messages and parameters."""
    for attempt in range(5, 0, -1):
        response = generate_with_schema(messages, **kwargs)
        try:
            text = response.text.strip()
            if text.startswith("```json"):
                start_idx = text.find("```json") + 7
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

def summarize_segment(translation_text: str, target_lang: str, model: str, show_params: bool) -> dict:
    """Summarize a single segment from its own translation text only, with no other context"""

    prompt = f"""Please write a summary of the following {target_lang} text segment.

[{target_lang} Text]
{translation_text}

[Summary Instructions]
1. Cover all major events, characters, and turns of content in this segment, not just the gist
2. Summarize only the content of this segment
3. Write in {target_lang}"""

    json_descriptions = create_json_descriptions_prompt(SegmentSummary)
    return generate(
        [prompt, json_descriptions],
        schema=SegmentSummary,
        model=model,
        show_params=show_params,
    )

def load_records(jsonl_file: str) -> list:
    records = []
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

def save_records(jsonl_file: str, records: list) -> None:
    with open(jsonl_file, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

def main():
    parser = argparse.ArgumentParser(description='Regenerate the summary field of a single segment record, using only that segment\'s own translation text as context')
    parser.add_argument('jsonl_file', help='JSONL file containing segment translations (e.g. ja.jsonl)')
    parser.add_argument('part', help='Part name (e.g. paradiso)')
    parser.add_argument('chapter', type=int, help='Chapter number')
    parser.add_argument('segment', type=int, help='Segment number')
    parser.add_argument('-m', '--model', required=True,
                       help='LLM model to use (e.g., gemini-2.5-pro, openai:gpt-5.6-luna)')

    args = parser.parse_args()

    records = load_records(args.jsonl_file)

    target = None
    for record in records:
        if (record['part'], record['chapter'], record['segment']) == (args.part, args.chapter, args.segment):
            target = record
            break

    if target is None:
        print(f"Error: record not found for {args.part} chapter {args.chapter} segment {args.segment}")
        return 1

    translation_text = target['response']['translation']
    target_lang = target['target_lang']
    old_summary = target['response']['summary']

    print(f"Regenerating summary for {args.part} chapter {args.chapter} segment {args.segment}...")
    print(f"Old summary: {old_summary}")

    result = summarize_segment(translation_text, target_lang, args.model, show_params=True)

    if not result or not result.get('summary'):
        print("Failed to generate summary")
        return 1

    target['response']['summary'] = result['summary']
    save_records(args.jsonl_file, records)

    print(f"New summary: {result['summary']}")
    print(f"Updated: {args.jsonl_file}")

    return 0

if __name__ == "__main__":
    exit(main())
