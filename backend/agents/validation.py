# agents\validation.py

import re
import json
import sys
from typing import Dict, Any, List, Tuple
from pathlib import Path
import logging
import pandas as pd
from .base import Talk2DrawingsBaseAgent

sys.path.append('..')

logger = logging.getLogger(__name__)


class ValidationAgent(Talk2DrawingsBaseAgent):

    # Cross-answer consistency rules: pairs of questions whose answers must be compatible
    CROSS_ANSWER_RULES = [
        {
            'name': 'seismic_site_class_consistency',
            'description': 'Seismic Design Category should be consistent with Site Class',
            'questions': {
                'sdc': [10],       # Q10: Seismic Design Category
                'site_class': [11] # Q11: Site Class
            },
            'check': '_check_seismic_site_class',
            'severity': 'high'
        },
        {
            'name': 'risk_category_importance_factor',
            'description': 'Risk Category and Importance Factor (Ie) must correspond',
            'questions': {
                'risk_category': [2],   # Q2: Risk Category
                'importance': [12]      # Q12: Importance Factor Ie
            },
            'check': '_check_risk_importance',
            'severity': 'high'
        },
        {
            'name': 'sds_sd1_relationship',
            'description': 'Sds should generally be greater than Sd1',
            'questions': {
                'sds': [13],  # Q13: Sds
                'sd1': [14]   # Q14: Sd1
            },
            'check': '_check_sds_sd1',
            'severity': 'medium'
        },
        {
            'name': 'snow_load_consistency',
            'description': 'Flat roof snow load Pf should be <= ground snow load Pg',
            'questions': {
                'pg': [24],  # Q24: Ground Snow Load
                'pf': [25]   # Q25: Flat Roof Snow Load
            },
            'check': '_check_snow_loads',
            'severity': 'medium'
        },
    ]

    # Risk Category -> valid Importance Factor mapping
    RISK_IMPORTANCE_MAP = {
        'I': [1.0], 'II': [1.0], 'III': [1.25], 'IV': [1.5]
    }

    def __init__(self, config: Dict[str, Any] = None, blackboard=None):
        super().__init__("Validation_Agent", blackboard=blackboard)
        self.config = config or {}
        self.limits_file = self.config.get('limits_file', 'limits.json')
        self.rules = (config or {}).get('validation_rules', {})
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
            answer_col = 'Main_Answer' if 'Main_Answer' in df.columns else 'Answer'
            standardized_count = 0
            if answer_col in df.columns:
                original = df[answer_col].astype(str)
                df['Normalized_Answer'] = original.apply(self.standardize_text_units)
                standardized_count = (original != df['Normalized_Answer']).sum()

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

            # --- Agentic: cross-answer contradiction detection ---
            answers_by_qid = self._extract_answers_by_qid(input_data)
            contradictions = self.detect_cross_answer_contradictions(answers_by_qid)
            suspicious = self.detect_suspicious_patterns(answers_by_qid)
            requery_suggestions = self.suggest_requeries(contradictions, suspicious)

            if contradictions:
                self.log_decision(
                    f"Found {len(contradictions)} cross-answer contradictions",
                    "; ".join(c['rule'] for c in contradictions),
                    decision_type="cross_validation"
                )
            if requery_suggestions:
                self.log_decision(
                    f"Suggesting requery for {len(requery_suggestions)} questions",
                    "; ".join(f"Q{s['question_id']}: {s['reason']}" for s in requery_suggestions),
                    decision_type="requery_suggestion"
                )

            print(f"Unit standardization: {standardized_count} answers modified")
            print(f"Validation completed: {status_counts}")
            print(f"Cross-answer contradictions: {len(contradictions)}")
            print(f"Suspicious patterns: {len(suspicious)}")
            print(f"Requery suggestions: {len(requery_suggestions)}")

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
                'units_standardized': standardized_count,
                'contradictions': contradictions,
                'suspicious_patterns': suspicious,
                'requery_suggestions': requery_suggestions}

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
            answer_col = 'Main_Answer' if 'Main_Answer' in question_data.columns else 'Answer'
            source_col = 'Source_PDF' if 'Source_PDF' in question_data.columns else None
            conf_col = 'OCR_Confidence' if 'OCR_Confidence' in question_data.columns else 'Confidence'
            unique_answers = question_data[answer_col].unique()
            if len(unique_answers) > 1:
                real_answers = [a for a in unique_answers if a != "Not Found"]
                if len(real_answers) > 1:
                    conflicts[question] = {
                        'conflicting_answers': real_answers,
                        'sources': question_data[source_col].tolist() if source_col else [],
                        'pages': question_data['Page'].tolist() if 'Page' in question_data.columns else [],
                        'confidence_scores': question_data[conf_col].tolist() if conf_col in question_data.columns else []}
        return conflicts

    # ------------------------------------------------------------------
    # Agentic: Cross-answer contradiction detection
    # ------------------------------------------------------------------

    def _extract_answers_by_qid(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract a {Q1: {answer, confidence, ...}, Q2: ...} dict from input."""
        if 'qa_results' in input_data:
            return input_data['qa_results']
        if 'results' in input_data:
            mapping = {}
            for item in input_data['results']:
                qnum = item.get('Question_Number')
                if qnum is not None:
                    mapping[f"Q{qnum}"] = item
            return mapping
        return {}

    def detect_cross_answer_contradictions(self, answers: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate cross-answer rules and return list of contradictions."""
        contradictions = []
        for rule in self.CROSS_ANSWER_RULES:
            check_method = getattr(self, rule['check'], None)
            if not check_method:
                continue
            try:
                result = check_method(answers, rule)
                if result:
                    contradictions.append({
                        'rule': rule['name'],
                        'description': rule['description'],
                        'severity': rule['severity'],
                        'details': result
                    })
            except Exception as e:
                logger.warning(f"Cross-answer check {rule['name']} failed: {e}")
        return contradictions

    def _get_answer_value(self, answers: Dict, qid: int) -> str:
        """Safely get the answer string for a question ID."""
        key = f"Q{qid}"
        entry = answers.get(key, {})
        if isinstance(entry, dict):
            return str(entry.get('answer', entry.get('Answer', ''))).strip()
        return str(entry).strip() if entry else ''

    def _check_seismic_site_class(self, answers: Dict, rule: Dict) -> Dict[str, Any] | None:
        sdc = self._get_answer_value(answers, rule['questions']['sdc'][0]).upper()
        site_class = self._get_answer_value(answers, rule['questions']['site_class'][0]).upper()
        if not sdc or not site_class or sdc == 'NOT FOUND' or site_class == 'NOT FOUND':
            return None
        # SDC D/E/F with Site Class A is suspicious
        if sdc in ('D', 'E', 'F') and site_class == 'A':
            return {
                'message': f"SDC={sdc} is unusual with Site Class A (hard rock)",
                'sdc': sdc, 'site_class': site_class,
                'affected_questions': [10, 11]
            }
        # SDC A with Site Class E/F is suspicious
        if sdc == 'A' and site_class in ('E', 'F'):
            return {
                'message': f"SDC=A is unusual with Site Class {site_class} (soft soil)",
                'sdc': sdc, 'site_class': site_class,
                'affected_questions': [10, 11]
            }
        return None

    def _check_risk_importance(self, answers: Dict, rule: Dict) -> Dict[str, Any] | None:
        risk_cat = self._get_answer_value(answers, rule['questions']['risk_category'][0]).upper().strip()
        ie_str = self._get_answer_value(answers, rule['questions']['importance'][0])
        if not risk_cat or not ie_str or risk_cat == 'NOT FOUND' or ie_str.upper() == 'NOT FOUND':
            return None
        ie_val = self.extract_first_float(ie_str)
        if ie_val is None:
            return None
        # Extract roman numeral from risk category string
        for rc in ['IV', 'III', 'II', 'I']:
            if rc in risk_cat:
                risk_cat = rc
                break
        valid = self.RISK_IMPORTANCE_MAP.get(risk_cat)
        if valid and ie_val not in valid:
            return {
                'message': f"Risk Category {risk_cat} expects Ie={valid}, got {ie_val}",
                'risk_category': risk_cat, 'ie': ie_val,
                'affected_questions': [2, 12]
            }
        return None

    def _check_sds_sd1(self, answers: Dict, rule: Dict) -> Dict[str, Any] | None:
        sds_str = self._get_answer_value(answers, rule['questions']['sds'][0])
        sd1_str = self._get_answer_value(answers, rule['questions']['sd1'][0])
        sds = self.extract_first_float(sds_str)
        sd1 = self.extract_first_float(sd1_str)
        if sds is None or sd1 is None:
            return None
        if sd1 > sds:
            return {
                'message': f"Sd1={sd1} > Sds={sds} is unusual (Sds typically > Sd1)",
                'sds': sds, 'sd1': sd1,
                'affected_questions': [13, 14]
            }
        return None

    def _check_snow_loads(self, answers: Dict, rule: Dict) -> Dict[str, Any] | None:
        pg_str = self._get_answer_value(answers, rule['questions']['pg'][0])
        pf_str = self._get_answer_value(answers, rule['questions']['pf'][0])
        pg = self.extract_first_float(pg_str)
        pf = self.extract_first_float(pf_str)
        if pg is None or pf is None:
            return None
        if pf > pg:
            return {
                'message': f"Flat roof snow Pf={pf} > Ground snow Pg={pg} (Pf should be <= Pg)",
                'pg': pg, 'pf': pf,
                'affected_questions': [24, 25]
            }
        return None

    def detect_suspicious_patterns(self, answers: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect suspicious answer patterns that suggest extraction problems."""
        suspicious = []

        # Check: too many "Not Found" in a single category
        from .qa import EngineeringQAAgent
        categories = getattr(EngineeringQAAgent, 'QUESTION_CATEGORIES', {})
        for cat_name, qids in categories.items():
            not_found_count = 0
            total = len(qids)
            for qid in qids:
                val = self._get_answer_value(answers, qid)
                if not val or val.upper() in ('NOT FOUND', 'N/A', 'NA', 'NONE', ''):
                    not_found_count += 1
            if total > 0 and not_found_count == total:
                suspicious.append({
                    'pattern': 'all_not_found_in_category',
                    'category': cat_name,
                    'question_ids': qids,
                    'message': f"All {total} questions in '{cat_name}' returned Not Found"
                })

        # Check: all deflection questions have identical answers (copy-paste artifact)
        deflection_qids = [3, 4, 5, 6, 7, 8]
        deflection_vals = []
        for qid in deflection_qids:
            val = self._get_answer_value(answers, qid)
            if val and val.upper() not in ('NOT FOUND', 'N/A', ''):
                deflection_vals.append(val)
        if len(deflection_vals) >= 4 and len(set(deflection_vals)) == 1:
            suspicious.append({
                'pattern': 'all_identical_deflections',
                'question_ids': deflection_qids,
                'value': deflection_vals[0],
                'message': f"All deflection limits are identical ({deflection_vals[0]}) — likely extraction error"
            })

        return suspicious

    def suggest_requeries(self, contradictions: List[Dict], suspicious: List[Dict]) -> List[Dict[str, Any]]:
        """Generate list of questions that should be re-queried based on issues found."""
        requery = []
        seen_qids = set()

        for c in contradictions:
            details = c.get('details', {})
            for qid in details.get('affected_questions', []):
                if qid not in seen_qids:
                    seen_qids.add(qid)
                    requery.append({
                        'question_id': qid,
                        'reason': f"Cross-answer contradiction: {c['rule']}",
                        'severity': c['severity'],
                        'source': 'contradiction'
                    })

        for s in suspicious:
            for qid in s.get('question_ids', []):
                if qid not in seen_qids:
                    seen_qids.add(qid)
                    requery.append({
                        'question_id': qid,
                        'reason': f"Suspicious pattern: {s['pattern']}",
                        'severity': 'medium',
                        'source': 'suspicious_pattern'
                    })

        return requery
