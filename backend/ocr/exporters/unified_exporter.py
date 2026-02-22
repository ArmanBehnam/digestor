# ocr/exporters/unified_exporter.py

import json
import csv
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

class UnifiedExporter:

    def __init__(self):
        self.supported_formats = ["json", "csv", "enhanced_csv"]

    def export_json(self, result, output_path: Path, pretty_print: bool = True):
        try:
            data = result.to_dict() if hasattr(result, 'to_dict') else result
        except:
            data = self._fallback_dict(result)

        with open(output_path, 'w', encoding='utf-8') as f:
            if pretty_print:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            else:
                json.dump(data, f, ensure_ascii=False, default=str)

    def export_csv(self, results: List[Dict], output_path: Path, questions: List[str]):
        with open(output_path, "w", newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Project', 'PDF', 'Page', 'Question', 'Answer', 'Source_Page', 'Confidence', 'Source'])

            for result in results:
                for i, q in enumerate(questions):
                    qid = f'Q{i+1}'
                    answer_data = result['answers'].get(qid, {})

                    if isinstance(answer_data, str):
                        answer = answer_data
                        source_page = 'N/A'
                        confidence = 'N/A'
                        source = 'Legacy'
                    else:
                        answer = answer_data.get('answer', 'Not Found')
                        source_page = answer_data.get('page', 'N/A')
                        confidence = answer_data.get('confidence', 0)
                        source = answer_data.get('source', 'OCR')

                    writer.writerow([
                        result['project'], result['pdf'], result['page'],
                        q, answer, source_page, f"{confidence}%", source
                    ])

    def export_enhanced_csv(self, results_dataframe: pd.DataFrame, output_path: Path):
        results_dataframe.to_csv(output_path, index=False, encoding='utf-8')

    def apply_deflection_defaults(self, df: pd.DataFrame, project_folder: str) -> pd.DataFrame:
        try:
            deflection_defaults = pd.read_csv("deflection_defaults.csv")
            deflection_map = dict(zip(deflection_defaults['Question'], deflection_defaults['DefaultAnswer']))

            new_rows = []
            for q in deflection_map.keys():
                if df[(df['Question'] == q) & (df['Answer'].str.lower() != 'nan')].empty:
                    new_rows.append({
                        'Project': Path(project_folder).name,
                        'PDF': 'default',
                        'Page': 'default',
                        'Question': q,
                        'Answer': deflection_map[q]
                    })

            if new_rows:
                df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
            return df
        except Exception as e:
            print(f"Warning: Could not apply deflection defaults: {e}")
            return df

    def _fallback_dict(self, result) -> Dict[str, Any]:
        return {
            'document_id': getattr(result, 'document_id', ''),
            'filename': getattr(result, 'filename', ''),
            'extracted_text': getattr(result, 'extracted_text', ''),
            'confidence': getattr(result, 'confidence', 0.0),
            'timestamp': datetime.now().isoformat()
        }

def create_unified_exporter():
    return UnifiedExporter()
