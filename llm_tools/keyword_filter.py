from rapidfuzz import fuzz
import re

class KeywordFilter:
    @staticmethod
    def match_keywords(text, keywords):
        text_lower = text.lower()
        matches = []
        for kw in keywords:
            kw_lower = kw.lower()
            if len(kw_lower) <= 3:
                if re.search(rf'\b{re.escape(kw_lower)}\b', text_lower):
                    matches.append(kw)
            else:
                if kw_lower in text_lower:
                    matches.append(kw)
        return matches

    @staticmethod
    def fuzzy_match_keywords(text, keywords, threshold=85):
        text_lower = text.lower()
        matches = []
        for kw in keywords:
            kw_lower = kw.lower()
            if len(kw_lower) <= 3:
                if re.search(rf'\b{re.escape(kw_lower)}\b', text_lower):
                    matches.append(kw)
            else:
                score = fuzz.partial_ratio(kw_lower, text_lower)
                if score >= threshold:
                    matches.append(kw)
        return matches

    @staticmethod
    def filter_pages(page_results, target_keywords, custom_keywords, category_keywords, category_threshold=2, fuzzy_flag=True):
        filtered_pages = []
        all_keywords = target_keywords + custom_keywords
        for page_data in page_results:
            page_text = page_data.get('extracted_text', '')
            if fuzzy_flag:
                matched_keywords = KeywordFilter.fuzzy_match_keywords(page_text, all_keywords)
                matched_category_keywords = KeywordFilter.fuzzy_match_keywords(page_text, category_keywords)
            else:
                matched_keywords = KeywordFilter.match_keywords(page_text, all_keywords)
                matched_category_keywords = KeywordFilter.match_keywords(page_text, category_keywords)
            if matched_keywords or len(matched_category_keywords) >= category_threshold:
                minimal_page = {
                    'page_number': page_data['page_number'],
                    'extracted_text': page_data['extracted_text'],
                    'matched_keywords': sorted(matched_keywords + matched_category_keywords, key=lambda k: page_text.lower().find(k.lower())),
                    'confidence_avg': page_data['confidence_avg'],
                    'element_count': page_data['element_count'],
                    'is_fallback': page_data.get('fallback_extraction', False)
                }
                filtered_pages.append(minimal_page)
        filtered_pages.sort(key=lambda p: (-len(p['matched_keywords']), p['page_number']))
        return filtered_pages