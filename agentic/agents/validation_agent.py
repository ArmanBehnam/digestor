# agents/merged_batch_workflow.py

import re
import json
import sys
from typing import Dict, Any, List, Tuple
from pathlib import Path
import pandas as pd
from .base_agent import Talk2DrawingsBaseAgent

sys.path.append('..')


class ValidationAgent(Talk2DrawingsBaseAgent):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("Validation_Agent")
        self.config = config or {}
        self.limits_file = self.config.get('limits_file', 'limits.json')
        self.rules = config.get('validation_rules', {})
        print(f"{self.name}: Loaded {len(self.rules)} validation rules")

    def _load_rules(self) -> Dict[str, Any]:
        try:
            limits_path = Path(self.limits_file)
            if not limits_path.exists():
                for possible_path in ['limits.json', '../limits.json', 'agentic/limits.json']:
                    if Path(possible_path).exists():
                        limits_path = Path(possible_path)
                        break

            with open(limits_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Could not load limits file: {e}")
            return {}

    def validate_input(self, input_data: Any) -> bool:
        return (isinstance(input_data, dict) and
                ('results_dataframe' in input_data or 'results' in input_data))

    async def process(self, input_data: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            if 'results_dataframe' in input_data:
                df = input_data['results_dataframe'].copy()
            elif 'results' in input_data:
                df = pd.DataFrame(input_data['results'])
            else:
                raise ValueError("No results data found to validate")
            df = self.normalize_colnames(df)
            standardized_count = 0
            if 'Main_Answer' in df.columns:
                original_answers = df['Main_Answer'].astype(str)
                df['Main_Answer'] = original_answers.apply(self.standardize_text_units)

            statuses, notes = [], []
            for _, row in df.iterrows():
                question = row.get('Question', '')
                answer = row.get('Main_Answer', '')
                status, note = self.validate_row(question, answer)
                statuses.append(status)
                notes.append(note)

            df['Validation_Status'] = statuses
            df['Validation_Notes'] = notes
            status_counts = df['Validation_Status'].value_counts().to_dict()
            conflicts = self.detect_conflicts(df)
            if conflicts:
                print(f"Conflicts detected in {len(conflicts)} questions")
                for question, conflict_data in conflicts.items():
                    print(f"  {question}: {len(conflict_data['conflicting_answers'])} different answers")

            print(f"Unit standardization: {standardized_count} answers modified")
            print(f"Validation completed: {status_counts}")

            return {'success': True,
                'agent': self.name,
                'validated_dataframe': df,
                'validation_summary': status_counts,
                'conflicts_detected': conflicts,
                'total_conflicts': len(conflicts),
                'total_validated': len(df),
                'passed': status_counts.get('OK', 0),
                'failed': status_counts.get('FAIL', 0),
                'skipped': status_counts.get('SKIP', 0),
                'units_standardized': standardized_count}

        except Exception as e:
            raise Exception(f"Validation processing failed: {e}")

    def extract_first_float(self, text: str):
        if not isinstance(text, str):
            return None
        m = re.search(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', text.replace(',', ''))
        return float(m.group()) if m else None

    def parse_all_floats(self, text: str):
        if not isinstance(text, str):
            return []
        return [float(x.replace(',', '')) for x in re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', text)]

    def parse_deflection(self, answer: str):
        if not isinstance(answer, str):
            return None
        m = re.search(r'[1Ll]\s*/\s*(\d{2,4})', answer)
        return float(m.group(1)) if m else None

    def normalize_colnames(self, df: pd.DataFrame):
        mapping = {}
        for c in df.columns:
            lc = c.strip().lower()
            if lc in ("question", "questions"):
                mapping[c] = "Question"
            elif lc in ("answer", "answers"):
                mapping[c] = "Answer"
            elif lc in ("answer", "answers", "main_answer", "main answer"):
                mapping[c] = "Main_Answer"
            elif lc in ("page", "page_number", "pageno"):
                mapping[c] = "Page"
            elif lc in ("file", "filename", "file_name"):
                mapping[c] = "Filename"
            elif lc in ("confidence", "conf", "score"):
                mapping[c] = "Confidence"
            else:
                mapping[c] = c
        return df.rename(columns=mapping)

    def evaluate_numeric_range(self, answer: str, rule: dict) -> Tuple[str, str]:
        val = self.extract_first_float(answer)
        if val is None:
            return "FAIL", "No numeric value found"
        lo = rule.get("min", None)
        hi = rule.get("max", None)
        unit = rule.get("unit", "")
        if lo is not None and val < lo:
            return "FAIL", f"{val} {unit} < min {lo} {unit}"
        if hi is not None and val > hi:
            return "FAIL", f"{val} {unit} > max {hi} {unit}"
        return "OK", f"{val} {unit} within [{lo}, {hi}]"

    def evaluate_any_in_range(self, answer: str, rule: dict) -> Tuple[str, str]:
        vals = self.parse_all_floats(answer)
        if not vals:
            return "FAIL", "No numeric values found"
        lo = rule.get("min", None)
        hi = rule.get("max", None)
        for v in vals:
            if (lo is None or v >= lo) and (hi is None or v <= hi):
                return "OK", f"Found {v} within [{lo}, {hi}]"
        return "FAIL", f"No values within [{lo}, {hi}] (found {vals})"

    def evaluate_deflection_min(self, answer: str, rule: dict) -> Tuple[str, str]:
        div = self.parse_deflection(answer)
        if div is None:
            return "FAIL", "No deflection pattern like L/### found"
        req = rule.get("min_divisor", None)
        if req is None:
            return "SKIP", "Rule missing min_divisor"
        if div >= req:
            return "OK", f"L/{int(div)} ≥ L/{int(req)}"
        return "FAIL", f"L/{int(div)} < L/{int(req)}"

    def evaluate_regex(self, answer: str, rule: dict) -> Tuple[str, str]:
        patt = rule.get("pattern", None)
        if not patt:
            return "SKIP", "Rule missing pattern"
        if not isinstance(answer, str):
            return "FAIL", "Answer not text"
        if re.search(patt, answer, flags=re.IGNORECASE):
            return "OK", "Pattern found"
        return "FAIL", "Pattern not found"

    def evaluate_enum(self, answer: str, rule: dict) -> Tuple[str, str]:
        allowed = rule.get("allowed", [])
        if not allowed:
            return "SKIP", "Rule missing allowed values"
        if not isinstance(answer, str):
            return "FAIL", "Answer not text"

        answer_lower = answer.lower()
        for allowed_val in allowed:
            if str(allowed_val).lower() in answer_lower:
                return "OK", f"Found allowed value: {allowed_val}"
        return "FAIL", f"None of {allowed} found in answer"

    def match_rule(self, question: str) -> Tuple[str, Dict]:
        if not isinstance(question, str):
            return None, None
        q = question.lower()
        for rule_name, rule in self.rules.items():
            needle = rule.get("match", rule_name).lower()
            if needle and needle in q:
                return rule_name, rule
        return None, None

    def validate_row(self, question: str, answer: str) -> Tuple[str, str]:
        rule_key, rule = self.match_rule(question)
        if not rule:
            return "SKIP", "No matching validation rule"

        rule_type = rule.get("type", None)
        evaluators = {"numeric_range": self.evaluate_numeric_range,
            "any_in_range": self.evaluate_any_in_range,
            "deflection_min": self.evaluate_deflection_min,
            "regex": self.evaluate_regex,
            "enum": self.evaluate_enum,}

        if not rule_type or rule_type not in evaluators:
            return "SKIP", f"Unknown rule type: {rule_type}"

        if isinstance(answer, str) and answer.strip().lower() in {"not found", "n/a", "na", "none"}:
            policy = rule.get("not_found", "fail")
            if policy == "ok":
                return "OK", "Answer 'Not Found' allowed by rule"
            if policy == "skip":
                return "SKIP", "Answer 'Not Found'—skipped by rule"
            return "FAIL", "Answer 'Not Found'"

        return evaluators[rule_type](answer, rule)

    def standardize_text_units(self, text: str) -> str:
        if not isinstance(text, str):
            return text
        text = re.sub(r'(\d+\.?\d*)\s*ft', r'\1 feet', text, flags=re.IGNORECASE)
        text = re.sub(r'(\d+\.?\d*)\s*feet', lambda m: f"{float(m.group(1)) * 12} inch", text)
        text = re.sub(r'(\d+\.?\d*)\s*ksi', lambda m: f"{float(m.group(1)) * 144000} psf", text)
        return text

    def detect_conflicts(self, df: pd.DataFrame) -> Dict[str, Any]:
        conflicts = {}
        for question in df['Question'].unique():
            question_data = df[df['Question'] == question]
            unique_answers = question_data['Main_Answer'].unique()
            if len(unique_answers) > 1:
                real_answers = [a for a in unique_answers if a != "Not Found"]
                if len(real_answers) > 1:
                    conflicts[question] = {
                        'conflicting_answers': real_answers,
                        'sources': question_data['Source_PDF'].tolist(),
                        'pages': question_data['Page'].tolist(),
                        'confidence_scores': question_data['OCR_Confidence'].tolist()}
        return conflicts