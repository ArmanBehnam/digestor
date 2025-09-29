import pandas as pd
import json
import re
from typing import List, Dict, Any


def parse_construction_json_to_dataframe(json_data: Dict[str, Any]) -> pd.DataFrame:


    results = []

    if 'filtered_pages_only' in json_data:
        pages = json_data['filtered_pages_only']
    else:
        pages = json_data.get('pages', [])

    for page in pages:
        page_number = page.get('page_number', 0)
        full_text = page.get('extracted_text', '')

        topics = extract_topics_from_text(full_text)

        for topic, content in topics.items():
            results.append({
                'page_number': page_number,
                'topic': topic,
                'text': content.strip(),
                'text_length': len(content.strip())
            })

    return pd.DataFrame(results)


def extract_topics_from_text(text: str) -> Dict[str, str]:

    topic_pattern = r'\b([A-Z][A-Z\s\(\)&\/\-\.]+?):\s*(?=\S)'

    topics = {}

    matches = list(re.finditer(topic_pattern, text))

    if not matches:
        return {"GENERAL NOTES": text}

    for i, match in enumerate(matches):
        topic_name = match.group(1).strip()

        if (len(topic_name) < 3 or
                re.search(r'^\d+$', topic_name) or
                topic_name in ['PSF', 'MPH', 'KSI', 'GRADE', 'TYPE']):
            continue

        start_pos = match.end()

        if i + 1 < len(matches):
            # Find the next valid topic
            for j in range(i + 1, len(matches)):
                next_topic = matches[j].group(1).strip()
                if (len(next_topic) >= 3 and
                        not re.search(r'^\d+$', next_topic) and
                        next_topic not in ['PSF', 'MPH', 'KSI', 'GRADE', 'TYPE']):
                    end_pos = matches[j].start()
                    break
            else:
                end_pos = len(text)
        else:
            end_pos = len(text)

        content = text[start_pos:end_pos].strip()

        topic_name = clean_topic_name(topic_name)

        if content and len(content) > 10:  # Only add if there's substantial content
            topics[topic_name] = content

    return topics


def clean_topic_name(topic: str) -> str:

    topic = re.sub(r'^\d+\.\s*', '', topic)  # Remove leading numbers
    topic = re.sub(r'^[A-Z]\.\s*', '', topic)  # Remove leading letters
    topic = topic.strip().rstrip(':')

    replacements = {
        'STRUCTURAL STEEL NOTES': 'STRUCTURAL STEEL',
        'CONCRETE NOTES': 'CONCRETE',
        'GENERAL STRUCTURAL NOTES': 'STRUCTURAL NOTES',
        'DESIGN CRITERIA': 'DESIGN CRITERIA',
        'REINFORCED MASONRY': 'MASONRY',
        'METAL ROOF DECK': 'ROOF DECK'
    }

    return replacements.get(topic, topic)


def get_topic_summary(df: pd.DataFrame) -> pd.DataFrame:

    if df.empty:
        return pd.DataFrame()

    summary = df.groupby('topic').agg({
        'text_length': ['count', 'sum', 'mean'],
        'confidence': 'mean',
        'page_number': lambda x: list(set(x))
    }).round(3)

    summary.columns = ['sections_count', 'total_text_length', 'avg_text_length', 'avg_confidence', 'pages']
    summary = summary.reset_index()

    summary = summary.sort_values('total_text_length', ascending=False)

    return summary


def save_construction_topics(json_data: Dict[str, Any], output_file: str = 'construction_topics.csv') -> None:

    doc_info = json_data.get('document_info', {})

    df = parse_construction_json_to_dataframe(json_data)

    metadata_lines = [
        f"# Document: {doc_info.get('filename', 'Unknown')}",
        f"# Document Type: {doc_info.get('document_type', 'Unknown')}",
        f"# Total Pages: {doc_info.get('total_pages', 0)}",
        f"# Processing Time: {doc_info.get('processing_time', 0):.1f}s",
        f"# Confidence: {doc_info.get('confidence', 0.0):.2f}",
        f"# Topics Found: {len(df['topic'].unique()) if not df.empty else 0}",
        "#"
    ]

    with open(output_file, 'w', encoding='utf-8') as f:
        for line in metadata_lines:
            f.write(line + '\n')

        df.to_csv(f, index=False)

    print(f"Saved {len(df)} topic entries to {output_file}")
    if not df.empty:
        print(f"Topics: {', '.join(df['topic'].unique())}")


if __name__ == "__main__":
    with open(r'\\ces-cdes\CDES_apps\NPD\Digestor\Test Cases\3_2409231029\GDCCC Drawings_result.json', 'r') as f:
        json_data = json.load(f)

    save_construction_topics(json_data)

    df = parse_construction_json_to_dataframe(json_data)