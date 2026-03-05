# ocr/processors/pattern.py

import re
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from collections import defaultdict

from ocr.core.interfaces import PatternProcessor
from ocr.core.models import DocumentType
from ocr.core.exceptions import PatternExtractionError
from ocr.config.patterns import get_patterns
from ocr.config.settings import get_config
from ocr.utils.text_utils import TextProcessor

logger = logging.getLogger(__name__)


class DocumentPatternProcessor(PatternProcessor):

    def __init__(self):
        self.config = get_config()
        self.patterns = get_patterns()
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}
        self._compile_patterns()

        self.engineering_terms = {
            'building_codes': ['IBC', 'OBC', 'NFPA', 'ASTM', 'AISI', 'ANSI', 'AWS', 'AISC'],
            'materials': ['Grade', 'gauge', 'steel', 'concrete', 'aluminum', 'wood'],
            'dimensions': ['SF', 'ft', 'in', 'mm', 'psf', 'PSF', 'ksi', 'MPa'],
            'standards': ['ASCE', 'AWS', 'AISC', 'TMS', 'ANSI', 'UL', 'FM'],
            'fire_protection': ['sprinkler', 'NFPA', 'fire', 'rating', 'resistance'],
            'structural': ['beam', 'column', 'joist', 'truss', 'foundation', 'footing']
        }
    
    def _compile_patterns(self) -> None:
        self._compiled_patterns = {}
        
        for category, pattern_list in self.patterns.get_patterns().items():
            compiled_list = []
            
            for pattern in pattern_list:
                try:
                    compiled_pattern = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                    compiled_list.append(compiled_pattern)
                except re.error as e:
                    logger.warning(f"Invalid regex pattern in {category}: {pattern} - {e}")
                    continue
            
            if compiled_list:
                self._compiled_patterns[category] = compiled_list
        
        logger.info(f"Compiled {sum(len(patterns) for patterns in self._compiled_patterns.values())} patterns")

    def extract_patterns(self, text: str) -> Dict[str, List[str]]:
        if not text or not text.strip():
            return {}

        results = {}

        try:
            for category, patterns in self._compiled_patterns.items():
                category_results = []

                for pattern in patterns:
                    try:
                        matches = pattern.findall(text)
                        if matches:
                            processed_matches = self._process_matches(matches)
                            if processed_matches:  # Check if not None/empty
                                category_results.extend(processed_matches)

                    except Exception as e:
                        logger.debug(f"Pattern extraction error in {category}: {e}")
                        continue

                if category_results:
                    cleaned_results = self._clean_and_deduplicate(category_results)
                    if cleaned_results:
                        results[category] = cleaned_results

            try:
                contextual_data = self._extract_contextual_data(text)
                if contextual_data:
                    results.update(contextual_data)
            except Exception as e:
                logger.debug(f"Contextual data extraction failed: {e}")

            try:
                analysis_data = self._analyze_document_structure(text)
                if analysis_data:
                    results.update(analysis_data)
            except Exception as e:
                logger.debug(f"Document structure analysis failed: {e}")

            # Filter out None/empty results
            filtered_results = {}
            for category, items in results.items():
                if items is not None:  # Check for None
                    if isinstance(items, list):
                        # Filter list items
                        filtered_items = []
                        for item in items:
                            if isinstance(item, str) and item and len(item.strip()) > 2:
                                filtered_items.append(item.strip())

                        if filtered_items:
                            filtered_results[category] = list(set(filtered_items))  # Dedup
                    elif isinstance(items, dict):
                        # Keep dictionaries as-is (document characteristics, etc.)
                        filtered_results[category] = items
                    elif isinstance(items, (int, float)):
                        # Keep numeric values as-is
                        filtered_results[category] = items
                    elif isinstance(items, str) and items.strip():
                        # Keep non-empty strings
                        filtered_results[category] = items.strip()

            return filtered_results

        except Exception as e:
            logger.error(f"Pattern extraction failed: {e}")
            return {}  # Return empty dict instead of raising exception

    def _process_matches(self, matches: List) -> List[str]:
        processed = []

        for match in matches:
            if isinstance(match, tuple):
                # Filter out empty groups
                valid_groups = [str(group).strip() for group in match if group and str(group).strip()]
                if valid_groups:
                    match_text = ' '.join(valid_groups)
                else:
                    continue  # Skip empty matches
            else:
                match_text = str(match).strip()

            if match_text and len(match_text) > 1:
                processed.append(match_text)

        return processed

    def _clean_and_deduplicate(self, results: List[str]) -> List[str]:
        if not results:  # Add this check
            return []

        cleaned = []
        seen = set()

        for result in results:
            cleaned_result = TextProcessor.clean_text(result)

            if (TextProcessor.is_valid_text(cleaned_result) and
                    cleaned_result.lower() not in seen):
                cleaned.append(cleaned_result)
                seen.add(cleaned_result.lower())

        return cleaned

    def _clean_result(self, result: str) -> str:
        if not result:
            return ""

        cleaned = re.sub(r'\s+', ' ', result.strip())
        cleaned = re.sub(r'^[-–—\s]+|[-–—\s]+$', '', cleaned)

        if cleaned in ['.', ',', ';', ':', '!', '?', '-', '_', '|']:
            return ""

        if len(cleaned) > 0:
            alpha_ratio = sum(1 for c in cleaned if c.isalnum()) / len(cleaned)
            if alpha_ratio < 0.3:
                return ""

        return cleaned
    
    def _extract_contextual_data(self, text: str) -> Dict[str, Any]:
        context_data = {}

        doc_type = self._detect_document_type(text)
        context_data['document_type'] = doc_type.value

        characteristics = self._analyze_document_characteristics(text)
        context_data['document_characteristics'] = characteristics

        if doc_type == DocumentType.CONSTRUCTION_SPEC:
            context_data.update(self._extract_specification_data(text))
        elif doc_type == DocumentType.ENGINEERING_DESIGN:
            context_data.update(self._extract_engineering_data(text))
        elif doc_type == DocumentType.FIRE_PROTECTION:
            context_data.update(self._extract_fire_protection_data(text))
        elif doc_type == DocumentType.MATERIAL_SPEC:
            context_data.update(self._extract_material_data(text))
        
        return context_data
    
    def _detect_document_type(self, text: str) -> DocumentType:
        text_lower = text.lower()
        
        type_indicators = {
            DocumentType.ARCHITECTURAL_PLAN: [
                'floor plan', 'elevation', 'building section', 'key plan', 'ada',
                'architectural', 'drawing', 'plan view', 'section view'
            ],
            DocumentType.CONSTRUCTION_SPEC: [
                'section', 'division', 'astm', 'part 1', 'part 2', 'part 3',
                'specification', 'submittal', 'quality assurance', 'execution'
            ],
            DocumentType.ENGINEERING_DESIGN: [
                'structural', 'foundation', 'framing', 'load', 'design criteria',
                'analysis', 'calculation', 'engineering', 'structural design'
            ],
            DocumentType.BUILDING_CODE: [
                'building code', 'fire code', 'occupancy', 'construction type',
                'ibc', 'obc', 'code compliance', 'regulatory'
            ],
            DocumentType.FIRE_PROTECTION: [
                'fire protection', 'sprinkler', 'nfpa', 'fire alarm', 'fire rating',
                'fire resistance', 'fire safety', 'suppression'
            ],
            DocumentType.MATERIAL_SPEC: [
                'material', 'product data', 'manufacturer', 'grade', 'type',
                'specification sheet', 'material properties', 'performance'
            ],
            DocumentType.TECHNICAL_MANUAL: [
                'manual', 'installation', 'procedure', 'maintenance', 'operation',
                'instructions', 'technical guide', 'handbook'
            ]
        }
        
        scores = {}
        for doc_type, indicators in type_indicators.items():
            score = sum(1 for indicator in indicators if indicator in text_lower)
            
            if doc_type == DocumentType.CONSTRUCTION_SPEC:
                section_count = len(re.findall(r'section\s+\d+', text_lower))
                division_count = len(re.findall(r'division\s+\d+', text_lower))
                score += (section_count + division_count) * 5
            
            if score > 0:
                scores[doc_type] = score
        
        if scores:
            return max(scores.keys(), key=lambda k: scores[k])
        
        return DocumentType.GENERAL
    
    def _analyze_document_characteristics(self, text: str) -> Dict[str, Any]:
        text_lower = text.lower()
        
        characteristics = {
            'has_technical_drawings': bool(re.search(r'elevation|plan|section|detail|drawing', text_lower)),
            'has_specifications': bool(re.search(r'specification|astm|section \d+', text_lower)),
            'has_building_codes': bool(re.search(r'building code|ibc|obc|nfpa', text_lower)),
            'has_dimensions': bool(re.search(r'\d+(?:\.\d+)?\s*(?:ft|in|mm|sf)', text_lower)),
            'has_materials': bool(re.search(r'steel|concrete|wood|masonry|aluminum', text_lower)),
            'has_fire_protection': bool(re.search(r'fire|sprinkler|nfpa|suppression', text_lower)),
            'has_structural_elements': bool(re.search(r'beam|column|joist|truss|foundation', text_lower)),
            'has_load_requirements': bool(re.search(r'load|psf|psi|ksi|mpa', text_lower)),
            'document_complexity': self._assess_complexity(text),
            'language_indicators': self._detect_language_patterns(text),
            'technical_density': self._calculate_technical_density(text)
        }
        
        return characteristics
    
    def _assess_complexity(self, text: str) -> str:
        indicators = {
            'simple': ['summary', 'general', 'basic', 'overview', 'introduction'],
            'moderate': ['specification', 'detail', 'requirements', 'standard', 'procedure'],
            'complex': ['engineering', 'structural', 'technical', 'analysis', 'calculation'],
            'very_complex': ['seismic', 'load analysis', 'finite element', 'computational', 'advanced']
        }
        
        text_lower = text.lower()
        scores = {}
        
        for level, terms in indicators.items():
            score = sum(1 for term in terms if term in text_lower)
            if level == 'very_complex':
                score *= 3
            elif level == 'complex':
                score *= 2
            scores[level] = score
        
        if scores:
            return max(scores.keys(), key=lambda k: scores[k])
        return 'moderate'
    
    def _detect_language_patterns(self, text: str) -> List[str]:
        patterns = {
            'regulatory': ['shall', 'comply', 'conform', 'required', 'mandatory', 'must'],
            'technical': ['specification', 'standard', 'grade', 'type', 'class', 'performance'],
            'procedural': ['install', 'apply', 'prepare', 'clean', 'provide', 'execute'],
            'quality': ['quality', 'assurance', 'control', 'inspection', 'testing', 'verification'],
            'safety': ['safety', 'hazard', 'warning', 'caution', 'protection', 'emergency'],
            'instructional': ['shall', 'should', 'must', 'required', 'ensure', 'verify']
        }
        
        text_lower = text.lower()
        detected = []
        
        for pattern_type, keywords in patterns.items():
            if any(keyword in text_lower for keyword in keywords):
                detected.append(pattern_type)
        
        return detected
    
    def _calculate_technical_density(self, text: str) -> float:
        if not text:
            return 0.0
        
        words = text.lower().split()
        total_words = len(words)
        
        if total_words == 0:
            return 0.0
        
        technical_count = 0
        
        for category, terms in self.engineering_terms.items():
            for term in terms:
                technical_count += sum(1 for word in words if term.lower() in word)
        
        return technical_count / total_words
    
    def _extract_specification_data(self, text: str) -> Dict[str, Any]:
        spec_data = {}
        
        division_pattern = r'(?:DIVISION|Division)\s+(\d+)\s*[-–—]\s*([^\n\r]+)'
        divisions = re.findall(division_pattern, text, re.IGNORECASE)
        if divisions:
            spec_data['divisions'] = [
                {'number': num.strip(), 'title': title.strip()}
                for num, title in divisions
            ]
        
        section_patterns = [
            r'(?:SECTION|Section)\s+(\d+(?:\s+\d+)*)\s*[-–—]\s*([^\n\r]+)',
            r'(\d{2}\s+\d{2}\s+\d{2})\s*[-–—]\s*([^\n\r]+)'  # CSI format
        ]
        
        sections = []
        for pattern in section_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            sections.extend([(num.strip(), title.strip()) for num, title in matches])
        
        if sections:
            spec_data['sections'] = [
                {'number': num, 'title': title} for num, title in sections
            ]
        
        part_pattern = r'PART\s+([123])[:\s]*([^\n\r]+)'
        parts = re.findall(part_pattern, text, re.IGNORECASE)
        if parts:
            spec_data['parts'] = [
                {'number': num, 'title': title.strip()} for num, title in parts
            ]
        
        return spec_data
    
    def _extract_engineering_data(self, text: str) -> Dict[str, Any]:
        eng_data = {}
        
        criteria_patterns = [
            r'(?:Design|design)\s+(?:criteria|requirements)[:\s]*([^\n]+)',
            r'(?:Performance|performance)\s+(?:criteria|requirements)[:\s]*([^\n]+)',
            r'(?:Load|LOAD)\s+(?:criteria|requirements)[:\s]*([^\n]+)',
        ]
        
        criteria = []
        for pattern in criteria_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            criteria.extend(match.strip() for match in matches)
        
        if criteria:
            eng_data['design_criteria'] = list(set(criteria))

        load_patterns = [
            r'(?:Dead|Live|Wind|Snow|Seismic)\s*Load[:\s]*(\d+(?:\.\d+)?)\s*(?:psf|PSF|kPa|kN/m2)',
            r'(?:Allowable|Ultimate)\s*(?:Stress|Strength)[:\s]*(\d+(?:\.\d+)?)\s*(?:ksi|MPa|psi)',
            r'(?:Deflection|DEFLECTION)[:\s]*(L\s*/\s*\d+)',
        ]
        
        loads = []
        for pattern in load_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            loads.extend(str(match) for match in matches)
        
        if loads:
            eng_data['structural_loads'] = list(set(loads))
        
        return eng_data
    
    def _extract_fire_protection_data(self, text: str) -> Dict[str, Any]:
        fire_data = {}

        rating_patterns = [
            r'(?:Fire\s*Rating|Fire\s*Resistance)[:\s]*(\d+(?:\.\d+)?)\s*(?:hour|hr)',
            r'(\d+)\s*(?:hour|hr)\s*(?:fire\s*)?(?:rating|resistance)',
            r'UL\s*([A-Z]?\d+)',
            r'FM\s*([A-Z]?\d+)'
        ]
        
        ratings = []
        for pattern in rating_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            ratings.extend(str(match) for match in matches)
        
        if ratings:
            fire_data['fire_ratings'] = list(set(ratings))

        nfpa_pattern = r'NFPA\s*(\d+[A-Z]?)'
        nfpa_standards = re.findall(nfpa_pattern, text, re.IGNORECASE)
        if nfpa_standards:
            fire_data['nfpa_standards'] = list(set(nfpa_standards))
        
        return fire_data
    
    def _extract_material_data(self, text: str) -> Dict[str, Any]:
        material_data = {}

        astm_pattern = r'ASTM\s*([A-Z]\s*\d+(?:[/-][A-Z]?\d+)*)'
        astm_standards = re.findall(astm_pattern, text, re.IGNORECASE)
        if astm_standards:
            material_data['astm_standards'] = list(set(astm_standards))

        grade_patterns = [
            r'Grade\s*([A-Z]?\d+[A-Z]*)',
            r'Type\s*([A-Z]?\d+[A-Z]*)',
            r'Class\s*([A-Z]?\d+[A-Z]*)'
        ]
        
        grades = []
        for pattern in grade_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            grades.extend(str(match) for match in matches)
        
        if grades:
            material_data['material_grades'] = list(set(grades))
        
        return material_data
    
    def _analyze_document_structure(self, text: str) -> Dict[str, Any]:
        structure_data = {}

        structure_data['paragraph_count'] = len(re.findall(r'\n\s*\n', text))
        structure_data['section_headers'] = len(re.findall(r'^[A-Z\s]+:?\s*$', text, re.MULTILINE))
        structure_data['numbered_items'] = len(re.findall(r'^\s*\d+[\.\)]\s+', text, re.MULTILINE))
        structure_data['bullet_points'] = len(re.findall(r'^\s*[•\-\*]\s+', text, re.MULTILINE))

        sentences = re.split(r'[.!?]+', text)
        if sentences:
            avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences)
            structure_data['avg_sentence_length'] = avg_sentence_length
            
            if avg_sentence_length > 25:
                structure_data['reading_complexity'] = 'high'
            elif avg_sentence_length > 15:
                structure_data['reading_complexity'] = 'medium'
            else:
                structure_data['reading_complexity'] = 'low'
        
        return structure_data
    
    def load_patterns(self, patterns: Dict[str, List[str]]) -> None:
        self.patterns.patterns = patterns
        self._compile_patterns()
        logger.info("Patterns reloaded and recompiled")
    
    def add_pattern(self, category: str, pattern: str) -> None:
        if not self.patterns.validate_pattern(pattern):
            raise PatternExtractionError(category, pattern, "Invalid regex pattern")
        
        self.patterns.add_pattern(category, pattern)
        
        if category in self.patterns.get_patterns():
            compiled_list = []
            for p in self.patterns.get_patterns()[category]:
                try:
                    compiled_pattern = re.compile(p, re.IGNORECASE | re.MULTILINE)
                    compiled_list.append(compiled_pattern)
                except re.error:
                    continue
            
            self._compiled_patterns[category] = compiled_list
        
        logger.info(f"Added pattern to category {category}")
    
    def get_pattern_statistics(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}
        
        stats = {
            'total_patterns': sum(len(patterns) for patterns in self._compiled_patterns.values()),
            'categories': len(self._compiled_patterns),
            'text_length': len(text),
            'matches_by_category': {},
            'top_categories': [],
            'coverage_analysis': {}
        }
        
        category_matches = {}
        
        for category, patterns in self._compiled_patterns.items():
            match_count = 0
            for pattern in patterns:
                matches = pattern.findall(text)
                match_count += len(matches)
            
            category_matches[category] = match_count
            stats['matches_by_category'][category] = match_count
        
        sorted_categories = sorted(category_matches.items(), key=lambda x: x[1], reverse=True)
        stats['top_categories'] = sorted_categories[:10]
        
        total_matches = sum(category_matches.values())
        stats['total_matches'] = total_matches
        stats['match_density'] = total_matches / len(text.split()) if text.split() else 0
        
        return stats


def create_pattern_processor() -> DocumentPatternProcessor:
    return DocumentPatternProcessor()