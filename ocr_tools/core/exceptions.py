from typing import Dict, Any, Optional, List


class PDFProcessorError(Exception):

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.context = context or {}
        self.message = message
    
    def __str__(self) -> str:
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} (Context: {context_str})"
        return self.message


class FileError(PDFProcessorError):
    pass


class FileNotFoundError(FileError):

    def __init__(self, file_path: str, context: Optional[Dict[str, Any]] = None):
        message = f"File not found: {file_path}"
        super().__init__(message, context)
        self.file_path = file_path


class UnsupportedFileTypeError(FileError):

    def __init__(self, file_path: str, file_type: str, supported_types: List[str]):
        message = f"Unsupported file type '{file_type}' for file '{file_path}'. Supported types: {', '.join(supported_types)}"
        context = {"file_path": file_path, "file_type": file_type, "supported_types": supported_types}
        super().__init__(message, context)
        self.file_type = file_type
        self.supported_types = supported_types


class FileCorruptedError(FileError):
    def __init__(self, file_path: str, details: str = ""):
        message = f"File corrupted or unreadable: {file_path}"
        if details:
            message += f" - {details}"
        super().__init__(message, {"file_path": file_path, "details": details})


class FileSizeLimitError(FileError):

    def __init__(self, file_path: str, file_size: int, max_size: int):
        message = f"File size ({file_size} bytes) exceeds limit ({max_size} bytes): {file_path}"
        context = {"file_path": file_path, "file_size": file_size, "max_size": max_size}
        super().__init__(message, context)


class OCRError(PDFProcessorError):
    pass


class OCREngineNotAvailableError(OCRError):

    def __init__(self, engine_name: str, reason: str = ""):
        message = f"OCR engine '{engine_name}' is not available"
        if reason:
            message += f": {reason}"
        super().__init__(message, {"engine_name": engine_name, "reason": reason})
        self.engine_name = engine_name


class OCRExtractionError(OCRError):

    def __init__(self, engine_name: str, page_number: int, details: str = ""):
        message = f"OCR extraction failed with engine '{engine_name}' on page {page_number}"
        if details:
            message += f": {details}"
        context = {"engine_name": engine_name, "page_number": page_number, "details": details}
        super().__init__(message, context)


class OCRConfigurationError(OCRError):

    def __init__(self, engine_name: str, missing_config: List[str]):
        message = f"OCR engine '{engine_name}' configuration error. Missing: {', '.join(missing_config)}"
        context = {"engine_name": engine_name, "missing_config": missing_config}
        super().__init__(message, context)


class OCRCredentialsError(OCRError):

    def __init__(self, service_name: str, details: str = ""):
        message = f"Invalid or missing credentials for {service_name}"
        if details:
            message += f": {details}"
        super().__init__(message, {"service_name": service_name, "details": details})


class ProcessingError(PDFProcessorError):
    pass


class ExtractionError(ProcessingError):

    def __init__(self, stage: str, document_id: str, details: str = ""):
        message = f"Extraction failed at stage '{stage}' for document {document_id}"
        if details:
            message += f": {details}"
        context = {"stage": stage, "document_id": document_id, "details": details}
        super().__init__(message, context)


class ImageProcessingError(ProcessingError):

    def __init__(self, operation: str, page_number: int, details: str = ""):
        message = f"Image processing failed during '{operation}' on page {page_number}"
        if details:
            message += f": {details}"
        context = {"operation": operation, "page_number": page_number, "details": details}
        super().__init__(message, context)


class TableDetectionError(ProcessingError):

    def __init__(self, page_number: int, method: str, details: str = ""):
        message = f"Table detection failed on page {page_number} using method '{method}'"
        if details:
            message += f": {details}"
        context = {"page_number": page_number, "method": method, "details": details}
        super().__init__(message, context)


class PatternExtractionError(ProcessingError):

    def __init__(self, pattern_category: str, pattern: str, details: str = ""):
        message = f"Pattern extraction failed for category '{pattern_category}'"
        if details:
            message += f": {details}"
        context = {"pattern_category": pattern_category, "pattern": pattern, "details": details}
        super().__init__(message, context)


class SpatialAnalysisError(ProcessingError):

    def __init__(self, analysis_type: str, details: str = ""):
        message = f"Spatial analysis failed for '{analysis_type}'"
        if details:
            message += f": {details}"
        super().__init__(message, {"analysis_type": analysis_type, "details": details})


class ValidationError(PDFProcessorError):
    pass


class GroundTruthValidationError(ValidationError):

    def __init__(self, validation_errors: List[str]):
        message = f"Ground truth validation failed: {'; '.join(validation_errors)}"
        super().__init__(message, {"validation_errors": validation_errors})
        self.validation_errors = validation_errors


class ConfigurationValidationError(ValidationError):

    def __init__(self, missing_keys: List[str], invalid_values: List[str] = None):
        errors = []
        if missing_keys:
            errors.append(f"Missing keys: {', '.join(missing_keys)}")
        if invalid_values:
            errors.append(f"Invalid values: {', '.join(invalid_values)}")
        
        message = f"Configuration validation failed: {'; '.join(errors)}"
        context = {"missing_keys": missing_keys, "invalid_values": invalid_values or []}
        super().__init__(message, context)


class ResultValidationError(ValidationError):

    def __init__(self, document_id: str, validation_issues: List[str]):
        message = f"Result validation failed for document {document_id}: {'; '.join(validation_issues)}"
        context = {"document_id": document_id, "validation_issues": validation_issues}
        super().__init__(message, context)


class EvaluationError(PDFProcessorError):
    pass


class MetricsCalculationError(EvaluationError):

    def __init__(self, metric_name: str, details: str = ""):
        message = f"Metrics calculation failed for '{metric_name}'"
        if details:
            message += f": {details}"
        super().__init__(message, {"metric_name": metric_name, "details": details})


class GroundTruthMismatchError(EvaluationError):

    def __init__(self, document_id: str, mismatches: List[str]):
        message = f"Ground truth mismatch for document {document_id}: {'; '.join(mismatches)}"
        context = {"document_id": document_id, "mismatches": mismatches}
        super().__init__(message, context)


class ExportError(PDFProcessorError):
    pass


class UnsupportedExportFormatError(ExportError):

    def __init__(self, format_name: str, supported_formats: List[str]):
        message = f"Unsupported export format '{format_name}'. Supported: {', '.join(supported_formats)}"
        context = {"format_name": format_name, "supported_formats": supported_formats}
        super().__init__(message, context)


class ExportValidationError(ExportError):

    def __init__(self, output_path: str, validation_errors: List[str]):
        message = f"Export validation failed for '{output_path}': {'; '.join(validation_errors)}"
        context = {"output_path": output_path, "validation_errors": validation_errors}
        super().__init__(message, context)


class ConfigurationError(PDFProcessorError):
    pass


class MissingConfigurationError(ConfigurationError):

    def __init__(self, config_key: str, config_file: str = ""):
        message = f"Missing required configuration: {config_key}"
        if config_file:
            message += f" in {config_file}"
        super().__init__(message, {"config_key": config_key, "config_file": config_file})


class InvalidConfigurationError(ConfigurationError):

    def __init__(self, config_key: str, value: Any, expected_type: str):
        message = f"Invalid configuration for '{config_key}': expected {expected_type}, got {type(value).__name__}"
        context = {"config_key": config_key, "value": value, "expected_type": expected_type}
        super().__init__(message, context)


class DependencyError(PDFProcessorError):
    pass


class MissingDependencyError(DependencyError):

    def __init__(self, dependency_name: str, install_instruction: str = ""):
        message = f"Missing required dependency: {dependency_name}"
        if install_instruction:
            message += f". Install with: {install_instruction}"
        super().__init__(message, {"dependency_name": dependency_name, "install_instruction": install_instruction})


class DependencyVersionError(DependencyError):

    def __init__(self, dependency_name: str, current_version: str, required_version: str):
        message = f"Incompatible version for {dependency_name}: {current_version} (required: {required_version})"
        context = {
            "dependency_name": dependency_name,
            "current_version": current_version,
            "required_version": required_version
        }
        super().__init__(message, context)


class ResourceError(PDFProcessorError):
    pass


class MemoryLimitError(ResourceError):

    def __init__(self, current_usage: int, limit: int):
        message = f"Memory usage ({current_usage} MB) exceeds limit ({limit} MB)"
        super().__init__(message, {"current_usage": current_usage, "limit": limit})


class TimeoutError(ResourceError):

    def __init__(self, operation: str, timeout_seconds: int):
        message = f"Operation '{operation}' timed out after {timeout_seconds} seconds"
        super().__init__(message, {"operation": operation, "timeout_seconds": timeout_seconds})


class CacheError(PDFProcessorError):
    pass


class CacheConnectionError(CacheError):

    def __init__(self, backend: str, details: str = ""):
        message = f"Cannot connect to cache backend '{backend}'"
        if details:
            message += f": {details}"
        super().__init__(message, {"backend": backend, "details": details})


class CacheKeyError(CacheError):

    def __init__(self, key: str, reason: str = ""):
        message = f"Invalid cache key: {key}"
        if reason:
            message += f" - {reason}"
        super().__init__(message, {"key": key, "reason": reason})


def handle_ocr_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "credentials" in str(e).lower():
                raise OCRCredentialsError("Unknown service", str(e))
            elif "not found" in str(e).lower():
                raise OCREngineNotAvailableError("Unknown engine", str(e))
            else:
                raise OCRExtractionError("Unknown engine", 0, str(e))

    return wrapper


def handle_file_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError as e:
            raise FileNotFoundError(str(e))
        except PermissionError as e:
            raise FileError(f"Permission denied: {e}")
        except IsADirectoryError as e:
            raise FileError(f"Expected file, got directory: {e}")
        except Exception as e:
            raise FileError(f"File operation failed: {e}")

    return wrapper


def create_context_error(base_exception: Exception, context: Dict[str, Any]) -> PDFProcessorError:
    if isinstance(base_exception, PDFProcessorError):
        base_exception.context.update(context)
        return base_exception

    return PDFProcessorError(str(base_exception), context)