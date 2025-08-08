from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
import uuid


class ElementType(Enum):
    TEXT = "text"
    TABLE = "table" 
    IMAGE = "image"
    DRAWING = "drawing"
    DIMENSION = "dimension"
    SIGNATURE = "signature"


class DocumentType(Enum):
    ARCHITECTURAL_PLAN = "architectural_plan"
    CONSTRUCTION_SPEC = "construction_specification"
    ENGINEERING_DESIGN = "engineering_design"
    BUILDING_CODE = "building_code"
    FIRE_PROTECTION = "fire_protection"
    MATERIAL_SPEC = "material_specification"
    TECHNICAL_MANUAL = "technical_manual"
    GENERAL = "general_construction_document"


class ProcessingMethod(Enum):
    PDF_ONLY = "pdf_only"
    OCR_ONLY = "ocr_only"
    HYBRID = "pdf_ocr_hybrid"


@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float
    confidence: float = 0.0
    
    def area(self) -> float:
        return self.width * self.height
    
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)
    
    def intersects(self, other: 'BoundingBox') -> bool:
        return not (
            self.x + self.width < other.x or
            other.x + other.width < self.x or
            self.y + self.height < other.y or
            other.y + other.height < self.y
        )
    
    def iou(self, other: 'BoundingBox') -> float:
        if not self.intersects(other):
            return 0.0
        
        x1 = max(self.x, other.x)
        y1 = max(self.y, other.y)
        x2 = min(self.x + self.width, other.x + other.width)
        y2 = min(self.y + self.height, other.y + other.height)
        
        intersection = (x2 - x1) * (y2 - y1)
        union = self.area() + other.area() - intersection
        
        return intersection / union if union > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'confidence': self.confidence
        }

@dataclass
class ExtractedElement:
    text: str
    element_type: ElementType
    page_number: int
    confidence: float = 0.0
    bbox: Optional[BoundingBox] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    element_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['element_type'] = self.element_type.value
        return result


@dataclass
class TableCell:
    content: str
    row_index: int
    col_index: int
    bbox: Optional[BoundingBox] = None
    confidence: float = 0.0
    
    def is_empty(self) -> bool:
        return not self.content or self.content.isspace()


@dataclass
class SpatialTable:
    rows: List[List[str]]
    headers: List[str]
    page_number: int
    confidence: float = 0.0
    bbox: Optional[BoundingBox] = None
    structure_type: str = "standard"
    table_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cells: List[TableCell] = field(default_factory=list)
    
    def get_cell(self, row: int, col: int) -> Optional[str]:
        if 0 <= row < len(self.rows) and 0 <= col < len(self.rows[row]):
            return self.rows[row][col]
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'table_id': self.table_id,
            'headers': self.headers,
            'rows': self.rows,
            'page_number': self.page_number,
            'confidence': self.confidence,
            'structure_type': self.structure_type,
            'bbox': asdict(self.bbox) if self.bbox else None,
            'cell_count': len(self.cells)
        }


@dataclass
class ImageInfo:
    image_id: str
    page_number: int
    format: str
    size: int  # File size in bytes
    dimensions: tuple[int, int]  # (width, height)
    bbox: Optional[BoundingBox] = None
    image_type: str = "embedded"  # embedded, extracted, processed
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingMetrics:
    total_elements: int = 0
    text_elements: int = 0
    table_elements: int = 0
    image_elements: int = 0
    avg_confidence: float = 0.0
    high_confidence_elements: int = 0
    low_confidence_elements: int = 0
    processing_time: float = 0.0
    memory_usage: float = 0.0
    
    def update_from_elements(self, elements: List[ExtractedElement]) -> None:
        self.total_elements = len(elements)
        if not elements:
            return

        type_counts = {}
        confidences = []
        
        for element in elements:
            element_type = element.element_type.value
            type_counts[element_type] = type_counts.get(element_type, 0) + 1
            confidences.append(element.confidence)
        
        self.text_elements = type_counts.get('text', 0)
        self.table_elements = type_counts.get('table', 0)
        self.image_elements = type_counts.get('image', 0)

        self.avg_confidence = sum(confidences) / len(confidences)
        self.high_confidence_elements = len([c for c in confidences if c > 0.7])
        self.low_confidence_elements = len([c for c in confidences if c < 0.3])


@dataclass
class ExtractionResult:
    document_id: str
    filename: str
    total_pages: int
    processing_method: ProcessingMethod
    document_type: DocumentType = DocumentType.GENERAL

    extracted_text: str = ""
    structured_data: Dict[str, Any] = field(default_factory=dict)
    tables: List[SpatialTable] = field(default_factory=list)
    elements: List[ExtractedElement] = field(default_factory=list)
    images: List[ImageInfo] = field(default_factory=list)

    spatial_analysis: Dict[str, Any] = field(default_factory=dict)

    confidence: float = 0.0
    processing_metrics: ProcessingMetrics = field(default_factory=ProcessingMetrics)

    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        self.processing_metrics.update_from_elements(self.elements)
    
    def add_element(self, element: ExtractedElement) -> None:
        self.elements.append(element)
        self.processing_metrics.update_from_elements(self.elements)
    
    def add_table(self, table: SpatialTable) -> None:
        self.tables.append(table)
    
    def get_elements_by_type(self, element_type: ElementType) -> List[ExtractedElement]:
        return [e for e in self.elements if e.element_type == element_type]
    
    def get_elements_by_page(self, page_number: int) -> List[ExtractedElement]:
        return [e for e in self.elements if e.page_number == page_number]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'document_id': self.document_id,
            'filename': self.filename,
            'total_pages': self.total_pages,
            'processing_method': self.processing_method.value,
            'document_type': self.document_type.value,
            'extracted_text': self.extracted_text,
            'structured_data': self.structured_data,
            'tables': [table.to_dict() for table in self.tables],
            'elements': [element.to_dict() for element in self.elements],
            'images': [asdict(img) for img in self.images],
            'spatial_analysis': self.spatial_analysis,
            'confidence': self.confidence,
            'processing_metrics': asdict(self.processing_metrics),
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class OCRMetrics:
    cer: float = 0.0
    wer: float = 0.0
    bleu_score: float = 0.0
    rouge_l: float = 0.0
    iou_scores: List[float] = field(default_factory=list)
    field_accuracy: Dict[str, float] = field(default_factory=dict)
    technical_accuracy: Dict[str, float] = field(default_factory=dict)
    
    def overall_score(self) -> float:

        text_score = max(0, 100 - (self.cer + self.wer) / 2)
        spatial_score = (sum(self.iou_scores) / len(self.iou_scores) * 100) if self.iou_scores else 50
        field_score = (sum(self.field_accuracy.values()) / len(self.field_accuracy)) if self.field_accuracy else 50
        
        return (text_score * 0.5 + spatial_score * 0.3 + field_score * 0.2)
    
    def quality_grade(self) -> str:
        if self.cer <= 2 and self.wer <= 5:
            return "EXCELLENT"
        elif self.cer <= 5 and self.wer <= 10:
            return "GOOD"
        elif self.cer <= 10 and self.wer <= 20:
            return "MODERATE"
        else:
            return "POOR"


@dataclass
class GroundTruthData:
    document_id: str
    source_file: str
    reference_text: str
    structured_fields: Dict[str, List[str]] = field(default_factory=dict)
    bounding_boxes: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    creation_date: datetime = field(default_factory=datetime.now)
    annotator: str = "unknown"
    
    def validate(self) -> bool:
        return bool(self.reference_text and self.source_file)

ElementList = List[ExtractedElement]
TableList = List[SpatialTable]
BBoxList = List[BoundingBox]