# backend/agents/supervisor.py
"""Supervisor Agent — monitors pipeline health, compiles final results, handles escalation."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from .base import Talk2DrawingsBaseAgent

logger = logging.getLogger(__name__)


class SupervisorAgent(Talk2DrawingsBaseAgent):
    """Top-level agent that monitors the pipeline and compiles final results.

    Responsibilities:
    - Evaluate overall pipeline health (OCR quality, QA confidence)
    - Decide whether to escalate to human review
    - Compile final results in the same format as the legacy orchestrator
    """

    # Thresholds (overridable via config)
    DEFAULT_OCR_QUALITY_THRESHOLD = 0.6
    DEFAULT_QA_CONFIDENCE_THRESHOLD = 0.5
    DEFAULT_NOT_FOUND_ESCALATION = 15
    DEFAULT_CONFIDENCE_ESCALATION = 40

    def __init__(self, config: Dict[str, Any] = None, blackboard=None):
        super().__init__("Supervisor_Agent", blackboard=blackboard)
        self.config = config or {}
        agentic_cfg = self.config.get('agentic', {})
        self.ocr_quality_threshold = agentic_cfg.get(
            'ocr_quality_threshold', self.DEFAULT_OCR_QUALITY_THRESHOLD)
        self.qa_confidence_threshold = agentic_cfg.get(
            'qa_confidence_threshold', self.DEFAULT_QA_CONFIDENCE_THRESHOLD)
        self.not_found_escalation = agentic_cfg.get(
            'not_found_escalation', self.DEFAULT_NOT_FOUND_ESCALATION)
        self.confidence_escalation = agentic_cfg.get(
            'confidence_escalation', self.DEFAULT_CONFIDENCE_ESCALATION)

    def validate_input(self, input_data: Any) -> bool:
        return isinstance(input_data, dict)

    async def process(self, input_data: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Evaluate pipeline output and compile final results."""
        health = self.evaluate_pipeline_health(input_data)
        should_escalate, escalation_reason = self.should_escalate_to_human(input_data)

        if should_escalate:
            self.log_decision(
                f"Escalation recommended: {escalation_reason}",
                f"Health: {health}",
                decision_type="escalation"
            )

        final_results = self.compile_final_results(input_data)

        return {
            'success': True,
            'agent': self.name,
            'health': health,
            'escalation_needed': should_escalate,
            'escalation_reason': escalation_reason if should_escalate else None,
            'final_results': final_results,
        }

    def evaluate_pipeline_health(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Check overall pipeline health from state."""
        health = {
            'ocr_quality': 'unknown',
            'qa_confidence': 'unknown',
            'validation_status': 'unknown',
            'overall': 'healthy',
            'issues': [],
        }

        # OCR quality
        ocr_quality = state.get('ocr_quality', None)
        if ocr_quality is not None:
            if ocr_quality >= self.ocr_quality_threshold:
                health['ocr_quality'] = 'good'
            else:
                health['ocr_quality'] = 'poor'
                health['issues'].append(f"OCR quality {ocr_quality:.2f} below threshold {self.ocr_quality_threshold}")

        # QA confidence
        qa_confidence = state.get('qa_confidence', None)
        if qa_confidence is not None:
            if qa_confidence >= self.qa_confidence_threshold:
                health['qa_confidence'] = 'good'
            else:
                health['qa_confidence'] = 'poor'
                health['issues'].append(f"QA confidence {qa_confidence:.2f} below threshold {self.qa_confidence_threshold}")

        # Validation
        validation = state.get('validation_result', {})
        contradictions = validation.get('contradictions', [])
        if contradictions:
            high_sev = [c for c in contradictions if c.get('severity') == 'high']
            if high_sev:
                health['validation_status'] = 'critical'
                health['issues'].append(f"{len(high_sev)} high-severity contradictions")
            else:
                health['validation_status'] = 'warning'

        # Error in state
        if state.get('error'):
            health['issues'].append(f"Pipeline error: {state['error']}")

        if health['issues']:
            health['overall'] = 'degraded' if len(health['issues']) <= 2 else 'unhealthy'

        return health

    def should_escalate_to_human(self, state: Dict[str, Any]) -> Tuple[bool, str]:
        """Determine if human review is needed."""
        reasons = []

        # Too many Not Found
        qa_result = state.get('qa_result', {})
        qa_results = qa_result.get('qa_results', {})
        not_found_count = 0
        for qid, val in qa_results.items():
            answer = val.get('answer', str(val)) if isinstance(val, dict) else str(val)
            if answer.strip().upper() in ('NOT FOUND', 'N/A', 'NA', 'NONE', ''):
                not_found_count += 1
        if not_found_count >= self.not_found_escalation:
            reasons.append(f"{not_found_count} questions returned Not Found")

        # Overall low confidence
        qa_confidence = state.get('qa_confidence', 100)
        if qa_confidence < self.confidence_escalation:
            reasons.append(f"Average confidence {qa_confidence:.1f}% below {self.confidence_escalation}%")

        # High-severity validation contradictions
        validation = state.get('validation_result', {})
        contradictions = validation.get('contradictions', [])
        high_sev = [c for c in contradictions if c.get('severity') == 'high']
        if high_sev:
            reasons.append(f"{len(high_sev)} high-severity cross-answer contradictions")

        if reasons:
            return True, "; ".join(reasons)
        return False, ""

    def compile_final_results(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Compile final results in the same format as the legacy orchestrator.

        Uses existing utility functions from backend/llm/utils.py.
        """
        from llm.utils import (
            apply_deflection_defaults_with_coordinates,
            normalize_answers_and_units,
            export_results_with_coordinates,
            format_coordinates_for_output,
        )

        qa_result = state.get('qa_result', {})
        ocr_result = state.get('ocr_result', {})
        raw_answers = qa_result.get('qa_results', {})
        questions = qa_result.get('questions', [])
        pdf_path = state.get('pdf_path', '')

        # Apply deflection defaults
        try:
            result = apply_deflection_defaults_with_coordinates(raw_answers, questions)
            processed_answers = result if isinstance(result, dict) else raw_answers
        except Exception as e:
            logger.warning(f"Deflection defaults failed: {e}")
            processed_answers = raw_answers

        # Normalize
        try:
            result = normalize_answers_and_units(processed_answers, questions)
            processed_answers = result if isinstance(result, dict) else processed_answers
        except Exception as e:
            logger.warning(f"Normalization failed: {e}")

        if not isinstance(processed_answers, dict):
            processed_answers = raw_answers if isinstance(raw_answers, dict) else {}

        # Build results rows
        results_data = []
        for i, question in enumerate(questions, 1):
            qid = f"Q{i}"
            answer_data = processed_answers.get(qid, {})

            if isinstance(answer_data, dict):
                answer = answer_data.get('answer', 'Not Found')
                page = answer_data.get('page', 'N/A')
                confidence = answer_data.get('confidence', 0)
                source = answer_data.get('source', 'Unknown')
                has_coordinates = answer_data.get('has_coordinates', False)
                coordinate_summary = answer_data.get('coordinate_summary')
                coordinates = answer_data.get('coordinates')
            else:
                answer = str(answer_data) if answer_data else 'Not Found'
                page = 'N/A'
                confidence = 0
                source = 'Legacy'
                has_coordinates = False
                coordinate_summary = None
                coordinates = None

            result_row = {
                'Question_Number': i,
                'Question': question,
                'Answer': answer,
                'Page': page,
                'Confidence': f"{confidence}%",
                'Source': source,
                'Deflection_Default': 'Applied' if source == 'deflection_defaults.csv' else '',
                'Has_Coordinates': 'Yes' if has_coordinates else 'No',
                'Coordinate_X': coordinate_summary.get('x', 0) if isinstance(coordinate_summary, dict) else 0,
                'Coordinate_Y': coordinate_summary.get('y', 0) if isinstance(coordinate_summary, dict) else 0,
                'Coordinate_Width': coordinate_summary.get('width', 0) if isinstance(coordinate_summary, dict) else 0,
                'Coordinate_Height': coordinate_summary.get('height', 0) if isinstance(coordinate_summary, dict) else 0,
                'Match_Type': coordinate_summary.get('match_type', 'none') if isinstance(coordinate_summary, dict) else 'none',
                'Match_Confidence': f"{coordinate_summary.get('match_confidence', 0):.1f}%" if isinstance(coordinate_summary, dict) else "0%",
                'Coordinates_Text': format_coordinates_for_output(coordinates) if coordinates else "No coordinates",
                'coordinates_full': coordinates,
                'has_coordinates': has_coordinates,
                'coordinate_summary': coordinate_summary,
            }
            results_data.append(result_row)

        # Build DataFrame and export
        df = pd.DataFrame(results_data)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        project_name = Path(pdf_path).stem if pdf_path else 'agentic'
        output_dir = str(Path(pdf_path).parent) if pdf_path else '.'

        try:
            export_paths = export_results_with_coordinates(
                results_data, output_dir, "pipeline_results_agentic", project_name
            )
        except Exception as e:
            logger.warning(f"Coordinate export failed: {e}")
            export_paths = {'csv_path': '', 'json_path': '', 'coordinate_success_rate': 0}

        # Standard CSV
        standard_csv = Path(output_dir) / f"pipeline_results_agentic_{project_name}_{timestamp}.csv"
        try:
            df.to_csv(standard_csv, index=False)
        except Exception as e:
            logger.warning(f"CSV export failed: {e}")

        # Summary JSON
        json_results = {
            'processing_mode': 'agentic',
            'document_info': ocr_result.get('document_info', {}),
            'coordinate_tracking': {
                'enabled': True,
                'algorithm': 'fuzzy_text_matching',
                'total_questions': len(questions),
            },
            'processing_summary': {
                'questions_total': len(questions),
                'questions_answered': len([r for r in results_data if r['Answer'] != 'Not Found']),
                'defaults_applied': len([r for r in results_data if r['Deflection_Default'] == 'Applied']),
                'timestamp': timestamp,
            },
            'pipeline_health': state.get('health', {}),
            'decisions_log': state.get('decisions_log', []),
            'results': results_data,
        }

        json_path = Path(output_dir) / f"pipeline_results_agentic_{project_name}_{timestamp}.json"
        try:
            with open(json_path, 'w') as f:
                json.dump(json_results, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"JSON export failed: {e}")

        return {
            'csv_path': str(standard_csv),
            'json_path': str(json_path),
            'coordinate_csv_path': export_paths.get('csv_path', ''),
            'coordinate_json_path': export_paths.get('json_path', ''),
            'results_dataframe': df,
            'summary': json_results['processing_summary'],
            'analysis_results': results_data,
        }
