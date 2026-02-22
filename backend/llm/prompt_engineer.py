# llm/prompt_engineer.py


import re
import logging
from typing import List, Dict, Any
from openai import OpenAI

logger = logging.getLogger(__name__)


class PromptEngineer:

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.prompt_config = config.get('prompt_engineering', {})
        self.enabled = self.prompt_config.get('enabled', False)
        self.optimization_level = self.prompt_config.get('optimization_level', 'balanced')
        self.cache_prompts = self.prompt_config.get('cache_prompts', True)

        self.openai_client = None
        if config.get('openai_api_key'):
            try:
                self.openai_client = OpenAI(api_key=config['openai_api_key'])
            except Exception as e:
                logger.warning(f"Could not initialize OpenAI for prompt optimization: {e}")

        self.prompt_cache = {}
        self.domain_patterns = {'structural': ['beam', 'column', 'load', 'stress', 'deflection', 'steel', 'concrete'],
            'seismic': ['seismic', 'earthquake', 'sds', 'sd1', 'response', 'spectral'],
            'wind': ['wind', 'pressure', 'gust', 'exposure', 'velocity'],
            'building_codes': ['ibc', 'building code', 'asce', 'aisc', 'aci'],
            'materials': ['concrete', 'steel', 'masonry', 'wood', 'composite'],
            'loads': ['dead load', 'live load', 'snow load', 'wind load', 'seismic load']}

        self.question_types = {'identification': ['what is', 'what are', 'identify', 'name'],
            'numerical': ['how much', 'how many', 'value', 'number', 'amount'],
            'specification': ['specification', 'requirement', 'standard', 'code'],
            'comparison': ['compare', 'difference', 'versus', 'vs'],
            'existence': ['is there', 'does', 'are there', 'exists']}

    def optimize_prompt(self, page_text: str, questions: List[str]) -> str:
        if not self.enabled:
            return self._generate_static_prompt(page_text, questions)

        cache_key = self._create_cache_key(page_text, questions)
        if self.cache_prompts and cache_key in self.prompt_cache:
            logger.debug("Using cached optimized prompt")
            return self.prompt_cache[cache_key]

        try:
            context_analysis = self._analyze_document_context(page_text)
            question_analysis = self._analyze_questions(questions)
            optimized_prompt = self._generate_optimized_prompt(page_text, questions, context_analysis, question_analysis)
            if self.cache_prompts:
                self.prompt_cache[cache_key] = optimized_prompt

            logger.info(f"Generated optimized prompt for {len(questions)} questions")
            return optimized_prompt
        except Exception as e:
            logger.error(f"Prompt optimization failed: {e}, falling back to static prompt")
            return self._generate_static_prompt(page_text, questions)

    def _analyze_document_context(self, text: str) -> Dict[str, Any]:
        analysis = {'domains': [], 'key_terms': [],'document_type': 'general', 'technical_level': 'medium',
            'contains_tables': False, 'contains_numbers': False, 'length_category': 'medium'}

        text_lower = text.lower()
        for domain, patterns in self.domain_patterns.items():
            if any(pattern in text_lower for pattern in patterns):
                analysis['domains'].append(domain)

        key_terms = re.findall(r'\\b[A-Z]{2,}\\b|\\b[A-Z]+\\d+\\b|\\b\\d+\\.\\d+\\b', text)
        analysis['key_terms'] = list(set(key_terms[:10]))
        if any(term in text_lower for term in ['specification', 'standard', 'code']):
            analysis['document_type'] = 'specification'
        elif any(term in text_lower for term in ['drawing', 'plan', 'detail']):
            analysis['document_type'] = 'drawing'
        elif any(term in text_lower for term in ['report', 'analysis', 'calculation']):
            analysis['document_type'] = 'report'

        technical_indicators = len(re.findall(r'\\b[A-Z]{3,}\\b', text))
        if technical_indicators > 20:
            analysis['technical_level'] = 'high'
        elif technical_indicators < 5:
            analysis['technical_level'] = 'low'

        analysis['contains_tables'] = bool(re.search(r'\\|.*\\|.*\\|', text))
        analysis['contains_numbers'] = bool(re.search(r'\\d+\\.?\\d*\\s*(?:mph|psf|pcf|ksi|psi)', text))
        if len(text) > 2000:
            analysis['length_category'] = 'long'
        elif len(text) < 500:
            analysis['length_category'] = 'short'

        return analysis

    def _analyze_questions(self, questions: List[str]) -> Dict[str, Any]:
        analysis = {'question_types': [], 'domains_requested': [],
            'complexity_level': 'medium', 'specific_formats': [], 'requires_calculation': False}

        for question in questions:
            q_lower = question.lower()
            for q_type, patterns in self.question_types.items():
                if any(pattern in q_lower for pattern in patterns):
                    analysis['question_types'].append(q_type)
                    break
            for domain, patterns in self.domain_patterns.items():
                if any(pattern in q_lower for pattern in patterns):
                    analysis['domains_requested'].append(domain)
            if 'version' in q_lower or 'year' in q_lower:
                analysis['specific_formats'].append('year_format')
            if 'ratio' in q_lower or 'l/' in q_lower:
                analysis['specific_formats'].append('ratio_format')
            if 'mph' in q_lower or 'psf' in q_lower or 'pcf' in q_lower:
                analysis['specific_formats'].append('unit_format')
            if any(term in q_lower for term in ['calculate', 'compute', 'determine']):
                analysis['requires_calculation'] = True
        if len(set(analysis['question_types'])) > 2 or analysis['requires_calculation']:
            analysis['complexity_level'] = 'high'
        elif len(analysis['question_types']) == 1 and analysis['question_types'][0] == 'identification':
            analysis['complexity_level'] = 'low'

        return analysis

    def _generate_optimized_prompt(self, page_text: str, questions: List[str], context_analysis: Dict, question_analysis: Dict) -> str:
        system_msg = self._generate_system_message(context_analysis, question_analysis)

        domain_instructions = self._generate_domain_instructions(context_analysis['domains'], question_analysis['domains_requested'])
        search_strategies = self._generate_search_strategies(question_analysis)
        format_specs = self._generate_format_specifications(question_analysis)
        error_handling = self._generate_error_handling_instructions(context_analysis)
        qblock = "\\n".join([f"Q{i+1}. {q}" for i, q in enumerate(questions)])
        prompt = f"""{system_msg}

**DOCUMENT CONTEXT ANALYSIS:**
- Document Type: {context_analysis['document_type'].title()}
- Engineering Domains: {', '.join(context_analysis['domains']) if context_analysis['domains'] else 'General'}
- Technical Level: {context_analysis['technical_level'].title()}
- Key Terms Detected: {', '.join(context_analysis['key_terms'][:5]) if context_analysis['key_terms'] else 'None'}

{domain_instructions}

{search_strategies}

{format_specs}

{error_handling}

**DOCUMENT TEXT:**
\\\"\\\"\\\"
{page_text}
\\\"\\\"\\\"

**QUESTIONS TO ANSWER:**
{qblock}

**OUTPUT FORMAT:**
For each question, provide your answer in this exact format:
Q[number]. [answer] | Page: [page_number] | Confidence: [percentage]%

**CRITICAL SUCCESS FACTORS:**
- Focus on EXACT matches and direct statements
- Include specific codes, standards, and numerical values with units
- Cross-reference multiple sections if needed
- Prioritize recent/authoritative information
- If uncertain, indicate specific areas of uncertainty rather than guessing
"""

        return prompt

    def _generate_system_message(self, context_analysis: Dict, question_analysis: Dict) -> str:
        if context_analysis['technical_level'] == 'high':
            expertise = "highly specialized structural and civil engineering expert with deep knowledge of building codes, standards, and technical specifications"
        elif context_analysis['technical_level'] == 'low':
            expertise = "knowledgeable engineering assistant skilled at extracting key information from technical documents"
        else:
            expertise = "expert engineering document analyst specializing in construction and structural engineering"

        complexity_note = ""
        if question_analysis['complexity_level'] == 'high':
            complexity_note = " You are dealing with complex technical questions that may require cross-referencing multiple sections and careful analysis."
        elif question_analysis['complexity_level'] == 'low':
            complexity_note = " Focus on clear, direct identification of the requested information."

        return f"You are a {expertise}.{complexity_note}"

    def _generate_domain_instructions(self, doc_domains: List[str], requested_domains: List[str]) -> str:
        relevant_domains = set(doc_domains + requested_domains)
        if not relevant_domains:
            return ""

        instructions = ["**DOMAIN-SPECIFIC GUIDANCE:**"]
        if 'building_codes' in relevant_domains:
            instructions.append("- Building Codes: Look for IBC, ASCE, AISC, ACI references with years (e.g., 'IBC 2018', 'ASCE 7-16')")
        if 'seismic' in relevant_domains:
            instructions.append("- Seismic Parameters: Search for Sds, Sd1, site class (A-F), seismic design category, importance factors")
        if 'wind' in relevant_domains:
            instructions.append("- Wind Loads: Look for wind speeds in mph, exposure categories (A/B/C), risk categories (I-IV)")
        if 'structural' in relevant_domains:
            instructions.append("- Structural Elements: Focus on deflection limits (L/240, L/360), load capacities, material properties")
        if 'loads' in relevant_domains:
            instructions.append("- Load Values: Extract values with units (psf, pcf, ksi), distinguish between dead, live, wind, snow loads")
        return "\\n".join(instructions)

    def _generate_search_strategies(self, question_analysis: Dict) -> str:
        strategies = ["**OPTIMIZED SEARCH STRATEGIES:**"]

        if 'identification' in question_analysis['question_types']:
            strategies.append("- For identification questions: Scan for proper nouns, standard codes, and explicit statements")
        if 'numerical' in question_analysis['question_types']:
            strategies.append("- For numerical questions: Look for numbers with units, ratios (L/xxx), percentages, and calculations")
        if 'specification' in question_analysis['question_types']:
            strategies.append("- For specifications: Search in sections titled 'Requirements', 'Standards', 'Criteria', or 'Specifications'")
        if 'existence' in question_analysis['question_types']:
            strategies.append("- For existence questions: Look for positive confirmations, section headings, or explicit mentions")
        if 'ratio_format' in question_analysis['specific_formats']:
            strategies.append("- Deflection ratios: Search for patterns like 'L/240', 'L/360', 'L/600' near deflection criteria")
        if 'year_format' in question_analysis['specific_formats']:
            strategies.append("- Year/Version info: Look for 4-digit years following code names or in document headers")
        return "\\n".join(strategies)

    def _generate_format_specifications(self, question_analysis: Dict) -> str:
        specs = ["**ANSWER FORMAT REQUIREMENTS:**"]
        if 'unit_format' in question_analysis['specific_formats']:
            specs.append("- Include units with numerical values (mph, psf, pcf, ksi, psi)")
        if 'ratio_format' in question_analysis['specific_formats']:
            specs.append("- Present ratios in standard format (e.g., L/240, not L divided by 240)")
        if 'year_format' in question_analysis['specific_formats']:
            specs.append("- Include years with code references (e.g., 'IBC 2018', not just 'IBC')")
        specs.append("- Preserve exact terminology and technical language from the document")
        specs.append("- Include relevant context when it adds clarity")
        return "\\n".join(specs)

    def _generate_error_handling_instructions(self, context_analysis: Dict) -> str:
        instructions = ["**OCR ERROR HANDLING:**"]
        if context_analysis['technical_level'] == 'high':
            instructions.append("- Be aware of OCR errors in technical terms (Sds vs SdS, Sd1 vs SD1)")
            instructions.append("- Watch for spacing issues in codes (ASCE 7-10 vs ASCE7-10)")

        instructions.append("- If multiple similar values exist, choose the most authoritative source")
        instructions.append("- For unclear text, focus on context clues and surrounding information")
        instructions.append("- Only return 'Not Found' when genuinely unable to locate any relevant information")

        return "\\n".join(instructions)

    def _generate_static_prompt(self, page_text: str, questions: List[str]) -> str:
        qblock = "\\n".join([f"Q{i+1}. {q}" for i, q in enumerate(questions)])
        return f"""You are a highly skilled engineering document interpreter specializing in construction documents.
        You will analyze OCR-extracted text from engineering documents to find answers to specific technical questions.

        **CRITICAL INSTRUCTIONS:**
        - OCR text may contain errors like character substitutions (e.g., 'Sd8' instead of 'Sds', 'windload' instead of 'wind load')
        - Be resilient to spacing issues, misaligned text, and OCR artifacts
        - Only return answers that are clearly supported by the document text
        - If an exact answer is not found, return "Not Found"
        - Do NOT guess or infer values
        - For deflection questions, search for ratios like L/240, L/360, L/600, etc.

        **SEARCH STRATEGIES BY CATEGORY:**

        **Building Codes:** Look for phrases like "building code", "IBC", "OBC", "CBC", "NYCBC" followed by years (2015, 2018, 2021, etc.)

        **ASCE Standards:** Search for "ASCE 7" followed by versions like "7-10", "7-16", "7-22"

        **Deflection Limits:** Search for:
        - Exterior walls: Look near "deflection criteria", "exterior wall", "curtain wall"
        - Interior walls: Look near "interior wall", "partition wall"
        - Floor joists: Look near "floor joist", "floor framing"
        - Roof rafters: Look near "roof rafter", "roof framing"
        - Ceiling joists: Look near "ceiling joist", "ceiling framing"
        - Primary structure: Look near "live load", "primary structure", "vertical deflection"

        **Wind Loads:** Search for "Vult", "wind speed", "mph", "exposure category" (A/B/C), "risk category" (I/II/III/IV), "GCpi"

        **Snow Loads:** Search for "Pg", "Is", "Ce", "Ct", "Pf" (often with = signs)

        **Seismic Parameters:** Search for "Sds", "Sd1", "site class" (A/B/C/D/E/F), "seismic design category", "Ie", "Ip"

        **Gravity Loads:** Search for "psf", "live load", "dead load", "roof"

        **COMMON OCR ERROR PATTERNS:**
        - "SdS" or "Sd8" → "Sds"
        - "SDl" or "SD1" → "Sd1"
        - "Windload" → "Wind load"
        - "L/240" might appear as "L/ 240" or "L /240"
        - Numbers may have extra spaces: "1 5 0" → "150"

        **OUTPUT FORMAT:**
        For each question, provide your answer in this exact format:
        Q[number]. [answer] | Page: [page_number] | Confidence: [percentage]%

        If not found, use:
        Q[number]. Not Found | Page: N/A | Confidence: 0%

        **DOCUMENT TEXT:**
        \\\"\\\"\\\"
        {page_text}
        \\\"\\\"\\\"

        **QUESTIONS TO ANSWER:**
        {qblock}

        **RESPONSE RULES:**
        - One clear, concise answer per question
        - Include page number if available in metadata
        - Provide confidence percentage (0-100%)
        - Use "Not Found" only when genuinely unable to locate the information
        - For deflection ratios, include the exact format found (e.g., "L/240", "L/360")
        - For codes, include year if present (e.g., "IBC 2018")
        - For numeric values, include units if specified (e.g., "150 mph", "20 psf")
        """

    def _create_cache_key(self, text: str, questions: List[str]) -> str:
        text_hash = hash(text[:1000])
        questions_hash = hash(tuple(questions))
        return f"{text_hash}_{questions_hash}_{self.optimization_level}"

    def get_optimization_stats(self) -> Dict[str, Any]:
        return {'enabled': self.enabled,
            'optimization_level': self.optimization_level,
            'cached_prompts': len(self.prompt_cache) if self.cache_prompts else 0,
            'openai_available': self.openai_client is not None}
