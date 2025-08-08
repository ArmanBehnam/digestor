from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import numpy as np

from ocr_tools.core.models import ExtractedElement, ExtractionResult, SpatialTable, BoundingBox, OCRMetrics, GroundTruthData, ElementType, DocumentType


class BaseExtractor(ABC):

    @abstractmethod
    def extract(self, source: Any, **kwargs) -> List[ExtractedElement]:
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass


class OCREngine(ABC):

    @abstractmethod
    def extract_text(self, image: np.ndarray, page_num: int, **kwargs) -> List[ExtractedElement]:
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        pass
    
    @abstractmethod
    def get_confidence_threshold(self) -> float:
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def priority(self) -> int:
        pass


class ImageProcessor(ABC):

    @abstractmethod
    def enhance_image(self, image: np.ndarray) -> np.ndarray:
        pass
    
    @abstractmethod
    def detect_tables(self, image: np.ndarray, page_num: int) -> List[ExtractedElement]:
        pass
    
    @abstractmethod
    def detect_technical_objects(self, image: np.ndarray, page_num: int) -> List[ExtractedElement]:
        pass


class PatternProcessor(ABC):

    @abstractmethod
    def extract_patterns(self, text: str) -> Dict[str, List[str]]:
        pass
    
    @abstractmethod
    def load_patterns(self, patterns: Dict[str, List[str]]) -> None:
        pass
    
    @abstractmethod
    def add_pattern(self, category: str, pattern: str) -> None:
        pass


class DocumentClassifier(ABC):

    @abstractmethod
    def classify(self, text: str, elements: List[ExtractedElement]) -> DocumentType:
        pass
    
    @abstractmethod
    def get_confidence(self, text: str, doc_type: DocumentType) -> float:
        pass


class SpatialAnalyzer(ABC):

    @abstractmethod
    def analyze_layout(self, elements: List[ExtractedElement], page_count: int) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def group_elements(self, elements: List[ExtractedElement]) -> List[List[ExtractedElement]]:
        pass
    
    @abstractmethod
    def calculate_coverage(self, elements: List[ExtractedElement]) -> float:
        pass


class MetricsCalculator(ABC):

    @abstractmethod
    def calculate_cer(self, ground_truth: str, predicted: str) -> float:
        pass
    
    @abstractmethod
    def calculate_wer(self, ground_truth: str, predicted: str) -> float:
        pass
    
    @abstractmethod
    def calculate_bleu(self, ground_truth: str, predicted: str, n: int = 4) -> float:
        pass
    
    @abstractmethod
    def calculate_rouge_l(self, ground_truth: str, predicted: str) -> float:
        pass
    
    @abstractmethod
    def calculate_iou(self, bbox1: BoundingBox, bbox2: BoundingBox) -> float:
        pass


class ResultEvaluator(ABC):

    @abstractmethod
    def evaluate(self, result: ExtractionResult, ground_truth: GroundTruthData) -> OCRMetrics:
        pass
    
    @abstractmethod
    def generate_report(self, metrics: OCRMetrics) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_recommendations(self, metrics: OCRMetrics) -> List[str]:
        pass


class BaseExporter(ABC):

    @abstractmethod
    def export(self, result: ExtractionResult, output_path: Path, **kwargs) -> None:
        pass
    
    @abstractmethod
    def validate_output(self, output_path: Path) -> bool:
        pass
    
    @property
    @abstractmethod
    def supported_formats(self) -> List[str]:
        pass


class GroundTruthManager(ABC):

    @abstractmethod
    def create_ground_truth(self, pdf_path: Path, **kwargs) -> GroundTruthData:
        pass
    
    @abstractmethod
    def load_ground_truth(self, gt_path: Path) -> GroundTruthData:
        pass
    
    @abstractmethod
    def save_ground_truth(self, ground_truth: GroundTruthData, output_path: Path) -> None:
        pass
    
    @abstractmethod
    def validate_ground_truth(self, ground_truth: GroundTruthData) -> bool:
        pass


class ConfigurationManager(ABC):

    @abstractmethod
    def load_config(self, config_path: Optional[Path] = None) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        pass


class ProcessingPipeline(ABC):

    @abstractmethod
    def process(self, input_path: Path, **kwargs) -> ExtractionResult:
        pass
    
    @abstractmethod
    def add_stage(self, stage: 'ProcessingStage') -> None:
        pass
    
    @abstractmethod
    def remove_stage(self, stage_name: str) -> None:
        pass
    
    @abstractmethod
    def get_pipeline_info(self) -> Dict[str, Any]:
        pass


class ProcessingStage(ABC):

    @abstractmethod
    def process(self, data: Any, context: Dict[str, Any]) -> Any:
        pass
    
    @abstractmethod
    def validate_input(self, data: Any) -> bool:
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def dependencies(self) -> List[str]:
        pass


class CacheManager(ABC):

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        pass
    
    @abstractmethod
    def clear(self) -> None:
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        pass


class LoggingManager(ABC):

    @abstractmethod
    def setup_logging(self, config: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    def log_processing_start(self, document_id: str, filename: str) -> None:
        pass
    
    @abstractmethod
    def log_processing_end(self, document_id: str, success: bool, metrics: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    def log_error(self, error: Exception, context: Dict[str, Any]) -> None:
        pass


class FileHandler(ABC):

    @abstractmethod
    def read_file(self, file_path: Path) -> bytes:
        pass
    
    @abstractmethod
    def write_file(self, file_path: Path, content: Union[str, bytes]) -> None:
        pass
    
    @abstractmethod
    def validate_file(self, file_path: Path, expected_type: str) -> bool:
        pass
    
    @abstractmethod
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        pass


class ImageHandler(ABC):

    @abstractmethod
    def load_image(self, image_data: bytes) -> np.ndarray:
        pass
    
    @abstractmethod
    def save_image(self, image: np.ndarray, output_path: Path, format: str = "PNG") -> None:
        pass
    
    @abstractmethod
    def resize_image(self, image: np.ndarray, target_size: tuple[int, int]) -> np.ndarray:
        pass
    
    @abstractmethod
    def convert_color_space(self, image: np.ndarray, target_space: str) -> np.ndarray:
        pass


class TextHandler(ABC):

    @abstractmethod
    def clean_text(self, text: str) -> str:
        pass
    
    @abstractmethod
    def extract_keywords(self, text: str) -> List[str]:
        pass
    
    @abstractmethod
    def calculate_similarity(self, text1: str, text2: str) -> float:
        pass
    
    @abstractmethod
    def detect_language(self, text: str) -> str:
        pass