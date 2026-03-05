# ocr/processors/image.py

import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from ocr.core.interfaces import ImageProcessor
from ocr.core.models import ExtractedElement, BoundingBox, ElementType
from ocr.core.exceptions import ImageProcessingError, DependencyError
from ocr.config.settings import get_config

logger = logging.getLogger(__name__)


class DocumentImageProcessor(ImageProcessor):

    def __init__(self):
        self.config = get_config()
        self._cv2 = None
        self._initialize_opencv()
    
    def _initialize_opencv(self) -> None:
        try:
            import cv2
            self._cv2 = cv2
            logger.info("Image processor initialized with OpenCV")
        except ImportError:
            logger.error("OpenCV not found. Install with: pip install opencv-python")
            raise DependencyError("opencv-python", "pip install opencv-python")
    
    def enhance_image(self, image: np.ndarray) -> np.ndarray:
        try:
            if image is None or image.size == 0:
                raise ValueError("Invalid input image")

            alpha = self.config.get('processing.image_enhancement_alpha', 1.2)
            beta = self.config.get('processing.image_enhancement_beta', 10)

            enhanced = self._cv2.convertScaleAbs(image, alpha=alpha, beta=beta)

            if self._needs_noise_reduction(enhanced):
                enhanced = self._reduce_noise(enhanced)
            
            if self._needs_contrast_enhancement(enhanced):
                enhanced = self._enhance_contrast(enhanced)
            
            if self._needs_sharpening(enhanced):
                enhanced = self._sharpen_image(enhanced)
            
            logger.debug("Image enhancement completed")
            return enhanced
            
        except Exception as e:
            logger.error(f"Image enhancement failed: {e}")
            raise ImageProcessingError("enhance_image", 0, str(e))
    
    def _needs_noise_reduction(self, image: np.ndarray) -> bool:
        try:
            gray = self._ensure_grayscale(image)

            laplacian_var = self._cv2.Laplacian(gray, self._cv2.CV_64F).var()

            return laplacian_var > 1000
            
        except:
            return False
    
    def _needs_contrast_enhancement(self, image: np.ndarray) -> bool:
        try:
            gray = self._ensure_grayscale(image)
            
            hist = self._cv2.calcHist([gray], [0], None, [256], [0, 256])

            hist_normalized = hist.flatten() / hist.sum()
            entropy = -np.sum(hist_normalized * np.log2(hist_normalized + 1e-10))

            return entropy < 6.0
            
        except:
            return False
    
    def _needs_sharpening(self, image: np.ndarray) -> bool:
        try:
            gray = self._ensure_grayscale(image)

            sobel_x = self._cv2.Sobel(gray, self._cv2.CV_64F, 1, 0, ksize=3)
            sobel_y = self._cv2.Sobel(gray, self._cv2.CV_64F, 0, 1, ksize=3)
            edge_strength = np.sqrt(sobel_x**2 + sobel_y**2).mean()

            return edge_strength < 20
            
        except:
            return False
    
    def _reduce_noise(self, image: np.ndarray) -> np.ndarray:
        try:
            if len(image.shape) == 3:

                return self._cv2.bilateralFilter(image, 9, 75, 75)
            else:
                return self._cv2.medianBlur(image, 5)
        except:
            return image
    
    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        try:
            if len(image.shape) == 3:
                lab = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2LAB)
                
                clahe = self._cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
                lab[:, :, 0] = clahe.apply(lab[:, :, 0])
                
                return self._cv2.cvtColor(lab, self._cv2.COLOR_LAB2BGR)
            else:
                # Grayscale
                clahe = self._cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                return clahe.apply(image)
        except:
            return image
    
    def _sharpen_image(self, image: np.ndarray) -> np.ndarray:
        try:
            blurred = self._cv2.GaussianBlur(image, (0, 0), 1.0)
            sharpened = self._cv2.addWeighted(image, 1.5, blurred, -0.5, 0)
            return sharpened
        except:
            return image
    
    def detect_tables(self, image: np.ndarray, page_num: int) -> List[ExtractedElement]:
        try:
            elements = []

            gray = self._ensure_grayscale(image)

            kernel_size = self.config.get('processing.table_line_kernel_size', 40)
            min_area = self.config.get('processing.table_min_area', 1000)
            confidence = self.config.get('processing.table_confidence_threshold', 0.7)
            
            # Line-based detection
            line_tables = self._detect_tables_by_lines(gray, page_num, kernel_size, min_area, confidence)
            elements.extend(line_tables)
            
            # Grid-based detection
            grid_tables = self._detect_tables_by_grid(gray, page_num, min_area, confidence)
            elements.extend(grid_tables)
            
            # Contour-based detection
            contour_tables = self._detect_tables_by_contours(gray, page_num, min_area, confidence)
            elements.extend(contour_tables)

            elements = self._remove_duplicate_tables(elements)
            
            logger.debug(f"Detected {len(elements)} table regions on page {page_num}")
            return elements
            
        except Exception as e:
            logger.error(f"Table detection failed: {e}")
            raise ImageProcessingError("table_detection", page_num, str(e))
    
    def _detect_tables_by_lines(self, gray: np.ndarray, page_num: int, 
                               kernel_size: int, min_area: int, confidence: float) -> List[ExtractedElement]:
        elements = []
        
        try:
            horizontal_kernel = self._cv2.getStructuringElement(self._cv2.MORPH_RECT, (kernel_size, 1))
            vertical_kernel = self._cv2.getStructuringElement(self._cv2.MORPH_RECT, (1, kernel_size))

            horizontal_lines = self._cv2.morphologyEx(gray, self._cv2.MORPH_OPEN, horizontal_kernel)
            vertical_lines = self._cv2.morphologyEx(gray, self._cv2.MORPH_OPEN, vertical_kernel)

            table_mask = self._cv2.addWeighted(horizontal_lines, 0.5, vertical_lines, 0.5, 0.0)

            contours, _ = self._cv2.findContours(table_mask, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = self._cv2.contourArea(contour)
                if area > min_area:
                    x, y, w, h = self._cv2.boundingRect(contour)

                    if w > 50 and h > 50 and (w / h < 10 and h / w < 10):
                        refined_bbox = self._refine_table_bbox(gray, x, y, w, h)
                        
                        bbox_data = {
                            'x': refined_bbox[0],
                            'y': refined_bbox[1], 
                            'width': refined_bbox[2],
                            'height': refined_bbox[3]
                        }
                        
                        element = ExtractedElement(
                            text="[TABLE_REGION]",
                            element_type=ElementType.TABLE,
                            page_number=page_num,
                            confidence=confidence,
                            bbox=BoundingBox(**bbox_data, confidence=confidence),
                            metadata={
                                'detection_method': 'line_detection',
                                'table_area': area,
                                'line_density': self._calculate_line_density(table_mask, x, y, w, h)
                            }
                        )
                        elements.append(element)
            
        except Exception as e:
            logger.debug(f"Line-based table detection failed: {e}")
        
        return elements
    
    def _detect_tables_by_grid(self, gray: np.ndarray, page_num: int, 
                              min_area: int, confidence: float) -> List[ExtractedElement]:
        elements = []
        
        try:
            thresh = self._cv2.adaptiveThreshold(
                gray, 255, self._cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                self._cv2.THRESH_BINARY_INV, 11, 2
            )

            contours, _ = self._cv2.findContours(thresh, self._cv2.RETR_TREE, self._cv2.CHAIN_APPROX_SIMPLE)

            potential_cells = []
            for contour in contours:
                x, y, w, h = self._cv2.boundingRect(contour)
                area = w * h

                if (20 < w < gray.shape[1] * 0.3 and 
                    10 < h < gray.shape[0] * 0.1 and 
                    area > 200):
                    
                    aspect_ratio = w / h
                    if 0.5 < aspect_ratio < 10:
                        potential_cells.append((x, y, w, h))

            tables = self._group_cells_into_tables(potential_cells, page_num, confidence)
            elements.extend(tables)
            
        except Exception as e:
            logger.debug(f"Grid-based table detection failed: {e}")
        
        return elements
    
    def _detect_tables_by_contours(self, gray: np.ndarray, page_num: int,
                                  min_area: int, confidence: float) -> List[ExtractedElement]:
        elements = []
        
        try:
            edges = self._cv2.Canny(gray, 50, 150)

            kernel = self._cv2.getStructuringElement(self._cv2.MORPH_RECT, (3, 3))
            dilated = self._cv2.dilate(edges, kernel, iterations=2)

            contours, _ = self._cv2.findContours(dilated, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = self._cv2.contourArea(contour)
                if area > min_area:
                    epsilon = 0.02 * self._cv2.arcLength(contour, True)
                    approx = self._cv2.approxPolyDP(contour, epsilon, True)
                    
                    if len(approx) >= 4:
                        x, y, w, h = self._cv2.boundingRect(contour)
                        
                        if (w > 100 and h > 50 and
                            w / h < 8 and h / w < 8):
                            
                            bbox_data = {'x': x, 'y': y, 'width': w, 'height': h}
                            
                            element = ExtractedElement(
                                text="[TABLE_REGION]",
                                element_type=ElementType.TABLE,
                                page_number=page_num,
                                confidence=confidence * 0.8,
                                bbox=BoundingBox(**bbox_data, confidence=confidence * 0.8),
                                metadata={
                                    'detection_method': 'contour_analysis',
                                    'contour_area': area,
                                    'approximation_vertices': len(approx)
                                }
                            )
                            elements.append(element)
            
        except Exception as e:
            logger.debug(f"Contour-based table detection failed: {e}")
        
        return elements
    
    def detect_technical_objects(self, image: np.ndarray, page_num: int) -> List[ExtractedElement]:
        try:
            elements = []
            
            gray = self._ensure_grayscale(image)

            dimension_elements = self._detect_dimension_lines(gray, page_num)
            elements.extend(dimension_elements)

            symbol_elements = self._detect_technical_symbols(gray, page_num)
            elements.extend(symbol_elements)

            arrow_elements = self._detect_arrows(gray, page_num)
            elements.extend(arrow_elements)
            
            logger.debug(f"Detected {len(elements)} technical objects on page {page_num}")
            return elements
            
        except Exception as e:
            logger.error(f"Technical object detection failed: {e}")
            raise ImageProcessingError("technical_object_detection", page_num, str(e))
    
    def _detect_dimension_lines(self, gray: np.ndarray, page_num: int) -> List[ExtractedElement]:
        elements = []
        
        try:
            horizontal_kernel = self._cv2.getStructuringElement(self._cv2.MORPH_RECT, (40, 1))
            vertical_kernel = self._cv2.getStructuringElement(self._cv2.MORPH_RECT, (1, 40))
            
            horizontal_lines = self._cv2.morphologyEx(gray, self._cv2.MORPH_OPEN, horizontal_kernel)
            vertical_lines = self._cv2.morphologyEx(gray, self._cv2.MORPH_OPEN, vertical_kernel)
            
            contours_h, _ = self._cv2.findContours(horizontal_lines, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours_h:
                x, y, w, h = self._cv2.boundingRect(contour)
                if w > 50 and h < 5:
                    element = self._create_dimension_element(x, y, w, h, page_num, 'horizontal_dimension')
                    elements.append(element)
            
            contours_v, _ = self._cv2.findContours(vertical_lines, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours_v:
                x, y, w, h = self._cv2.boundingRect(contour)
                if h > 50 and w < 5:
                    element = self._create_dimension_element(x, y, w, h, page_num, 'vertical_dimension')
                    elements.append(element)
            
        except Exception as e:
            logger.debug(f"Dimension line detection failed: {e}")
        
        return elements
    
    def _detect_technical_symbols(self, gray: np.ndarray, page_num: int) -> List[ExtractedElement]:
        elements = []
        
        try:
            circles = self._cv2.HoughCircles(
                gray, self._cv2.HOUGH_GRADIENT, 1, 20,
                param1=50, param2=30, minRadius=5, maxRadius=50
            )
            
            if circles is not None:
                circles = np.round(circles[0, :]).astype("int")
                
                for (x, y, r) in circles:
                    bbox_data = {
                        'x': x - r,
                        'y': y - r,
                        'width': 2 * r,
                        'height': 2 * r
                    }
                    
                    element = ExtractedElement(
                        text="[TECHNICAL_SYMBOL]",
                        element_type=ElementType.DRAWING,
                        page_number=page_num,
                        confidence=0.6,
                        bbox=BoundingBox(**bbox_data, confidence=0.6),
                        metadata={
                            'symbol_type': 'circle',
                            'radius': r,
                            'center': (x, y)
                        }
                    )
                    elements.append(element)
            
        except Exception as e:
            logger.debug(f"Technical symbol detection failed: {e}")
        
        return elements
    
    def _detect_arrows(self, gray: np.ndarray, page_num: int) -> List[ExtractedElement]:
        elements = []
        try:
            corners = self._cv2.goodFeaturesToTrack(gray, 100, 0.01, 10)
            
            if corners is not None:
                for corner in corners:
                    x, y = corner.ravel()
                    x, y = int(x), int(y)

                    if self._is_arrow_like_region(gray, x, y):
                        bbox_data = {
                            'x': x - 10,
                            'y': y - 10,
                            'width': 20,
                            'height': 20
                        }
                        
                        element = ExtractedElement(
                            text="[ARROW/POINTER]",
                            element_type=ElementType.DRAWING,
                            page_number=page_num,
                            confidence=0.5,
                            bbox=BoundingBox(**bbox_data, confidence=0.5),
                            metadata={
                                'symbol_type': 'arrow_candidate',
                                'corner_point': (x, y)
                            }
                        )
                        elements.append(element)
            
        except Exception as e:
            logger.debug(f"Arrow detection failed: {e}")
        
        return elements
    
    def _ensure_grayscale(self, image: np.ndarray) -> np.ndarray:
        if len(image.shape) == 3:
            return self._cv2.cvtColor(image, self._cv2.COLOR_BGR2GRAY)
        return image
    
    def _refine_table_bbox(self, gray: np.ndarray, x: int, y: int, w: int, h: int) -> Tuple[int, int, int, int]:
        try:
            table_region = gray[y:y + h, x:x + w]

            rows_with_content = np.where(np.sum(table_region < 200, axis=1) > 5)[0]
            cols_with_content = np.where(np.sum(table_region < 200, axis=0) > 5)[0]
            
            if len(rows_with_content) > 0 and len(cols_with_content) > 0:
                new_y = y + rows_with_content[0]
                new_x = x + cols_with_content[0]
                new_h = rows_with_content[-1] - rows_with_content[0]
                new_w = cols_with_content[-1] - cols_with_content[0]
                
                return (new_x, new_y, new_w, new_h)
            
        except Exception:
            pass
        
        return (x, y, w, h)
    
    def _calculate_line_density(self, mask: np.ndarray, x: int, y: int, w: int, h: int) -> float:
        try:
            region = mask[y:y + h, x:x + w]
            line_pixels = np.sum(region > 0)
            total_pixels = w * h
            return line_pixels / total_pixels if total_pixels > 0 else 0.0
        except:
            return 0.0
    
    def _group_cells_into_tables(self, cells: List[Tuple[int, int, int, int]], 
                                page_num: int, confidence: float) -> List[ExtractedElement]:
        if not cells:
            return []

        cells.sort(key=lambda cell: (cell[1], cell[0]))
        
        tables = []
        current_table_cells = []
        last_y = cells[0][1]
        
        for cell in cells:
            x, y, w, h = cell

            if abs(y - last_y) > h * 2:
                if len(current_table_cells) >= 4:
                    table_element = self._create_table_from_cells(current_table_cells, page_num, confidence)
                    if table_element:
                        tables.append(table_element)
                current_table_cells = [cell]
            else:
                current_table_cells.append(cell)
            
            last_y = y

        if len(current_table_cells) >= 4:
            table_element = self._create_table_from_cells(current_table_cells, page_num, confidence)
            if table_element:
                tables.append(table_element)
        
        return tables
    
    def _create_table_from_cells(self, cells: List[Tuple[int, int, int, int]], 
                                page_num: int, confidence: float) -> Optional[ExtractedElement]:
        if not cells:
            return None

        min_x = min(cell[0] for cell in cells)
        min_y = min(cell[1] for cell in cells)
        max_x = max(cell[0] + cell[2] for cell in cells)
        max_y = max(cell[1] + cell[3] for cell in cells)
        
        bbox_data = {
            'x': min_x,
            'y': min_y,
            'width': max_x - min_x,
            'height': max_y - min_y
        }
        
        return ExtractedElement(
            text="[TABLE_REGION]",
            element_type=ElementType.TABLE,
            page_number=page_num,
            confidence=confidence * 0.9,
            bbox=BoundingBox(**bbox_data, confidence=confidence * 0.9),
            metadata={
                'detection_method': 'cell_grouping',
                'cell_count': len(cells),
                'cells': cells
            }
        )
    
    def _create_dimension_element(self, x: int, y: int, w: int, h: int, 
                                 page_num: int, dimension_type: str) -> ExtractedElement:
        bbox_data = {'x': x, 'y': y, 'width': w, 'height': h}
        
        return ExtractedElement(
            text="[DIMENSION_LINE]",
            element_type=ElementType.DIMENSION,
            page_number=page_num,
            confidence=0.7,
            bbox=BoundingBox(**bbox_data, confidence=0.7),
            metadata={
                'detection_method': 'line_detection',
                'dimension_type': dimension_type,
                'length': w if dimension_type == 'horizontal_dimension' else h
            }
        )
    
    def _is_arrow_like_region(self, gray: np.ndarray, x: int, y: int, size: int = 20) -> bool:
        try:
            half_size = size // 2
            y1, y2 = max(0, y - half_size), min(gray.shape[0], y + half_size)
            x1, x2 = max(0, x - half_size), min(gray.shape[1], x + half_size)
            
            region = gray[y1:y2, x1:x2]
            
            if region.size == 0:
                return False

            edges = self._cv2.Canny(region, 50, 150)
            contours, _ = self._cv2.findContours(edges, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                epsilon = 0.02 * self._cv2.arcLength(contour, True)
                approx = self._cv2.approxPolyDP(contour, epsilon, True)
                
                if len(approx) == 3:
                    return True
            
            return False
            
        except:
            return False
    
    def _remove_duplicate_tables(self, elements: List[ExtractedElement]) -> List[ExtractedElement]:
        if not elements:
            return elements

        elements.sort(key=lambda e: e.confidence, reverse=True)
        
        filtered = []
        for element in elements:
            is_duplicate = False
            
            for existing in filtered:
                if element.bbox and existing.bbox:
                    overlap = element.bbox.iou(existing.bbox)
                    if overlap > 0.5:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                filtered.append(element)
        
        return filtered


def create_image_processor() -> DocumentImageProcessor:
    return DocumentImageProcessor()