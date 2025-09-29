# ocr/config/settings.py

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
import logging

from ocr.core.interfaces import ConfigurationManager
from ocr.core.exceptions import ConfigurationError, MissingConfigurationError, InvalidConfigurationError, ConfigurationValidationError



@dataclass
class OCRConfig:
    preferred_engine: str = "aws_textract"
    fallback_engines: List[str] = field(default_factory=lambda: [   # "azure_ocr",
         "claude_ocr", "mistral_ocr", "tesseract", "opencv"
    ])
    confidence_threshold: float = 0.5
    timeout_seconds: int = 120
    max_retries: int = 3

    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None

    azure_endpoint: Optional[str] = None
    azure_api_key: Optional[str] = None

    claude_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    claude_max_tokens: int = 4000

    mistral_api_key: Optional[str] = None

    tesseract_cmd: Optional[str] = None
    tesseract_configs: List[str] = field(default_factory=lambda: [
        # '--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,;:!?()[]{}/-" ',
        # '--psm 4 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,;:!?()[]{}/-" ',
        '--psm 3'
        # '--psm 11'
    ])
@dataclass
class ProcessingConfig:
    """Document processing configuration."""
    use_ocr: bool = True
    use_pdf_text: bool = True
    use_image_enhancement: bool = True
    use_table_detection: bool = True
    use_spatial_analysis: bool = True
    use_pattern_extraction: bool = True
    
    image_scale_factor: float = 2.0
    image_enhancement_alpha: float = 1.2
    image_enhancement_beta: int = 10
    max_image_size: int = 10 * 1024 * 1024  # 10MB
    
    table_min_area: int = 1000
    table_line_kernel_size: int = 40
    table_confidence_threshold: float = 0.7

    min_text_confidence: float = 0.3
    min_text_length: int = 2
    text_cleaning_enabled: bool = True


@dataclass
class EvaluationConfig:
    calculate_cer: bool = True
    calculate_wer: bool = True
    calculate_bleu: bool = True
    calculate_rouge_l: bool = True
    calculate_iou: bool = True
    calculate_field_accuracy: bool = True
    calculate_technical_accuracy: bool = True
    
    excellent_cer_threshold: float = 2.0
    excellent_wer_threshold: float = 5.0
    good_cer_threshold: float = 5.0
    good_wer_threshold: float = 10.0
    moderate_cer_threshold: float = 10.0
    moderate_wer_threshold: float = 20.0
    
    iou_threshold_50: float = 0.5
    iou_threshold_75: float = 0.75


@dataclass
class ExportConfig:
    default_format: str = "json"
    supported_formats: List[str] = field(default_factory=lambda: ["json", "csv", "structured_table"])
    output_directory: str = "output"
    include_metadata: bool = True
    include_confidence_scores: bool = True
    include_bounding_boxes: bool = True
    pretty_print_json: bool = True


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = None
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    console_output: bool = True


@dataclass
class CacheConfig:
    enabled: bool = False
    backend: str = "memory"  # memory, redis, file
    ttl_seconds: int = 3600  # 1 hour
    max_size: int = 1000
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    file_cache_dir: str = ".cache"


@dataclass
class PerformanceConfig:
    max_memory_mb: int = 4 * 1024  # 4GB
    max_processing_time_seconds: int = 300  # 5 minutes
    parallel_processing: bool = False
    max_workers: int = 4
    chunk_size: int = 1000
    enable_profiling: bool = False


@dataclass
class SecurityConfig:
    validate_file_types: bool = True
    allowed_file_extensions: List[str] = field(default_factory=lambda: [".pdf", ".dwg"])
    max_file_size_mb: int = 100
    scan_for_malware: bool = False
    sanitize_output: bool = True


@dataclass
class ApplicationConfig:
    ocr: OCRConfig = field(default_factory=OCRConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    debug: bool = False
    version: str = "1.0.0"
    environment: str = "production"


class ConfigManager(ConfigurationManager):

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self.config = ApplicationConfig()
        self._load_config()
    
    def _load_config(self) -> None:
        self._load_from_environment()

        if self.config_path and self.config_path.exists():
            self._load_from_file(self.config_path)

        default_config = Path("config.json")
        if default_config.exists():
            self._load_from_file(default_config)

        self.validate_config()
    
    def _load_from_environment(self) -> None:

        if os.getenv("AWS_ACCESS_KEY_ID"):
            self.config.ocr.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        if os.getenv("AWS_SECRET_ACCESS_KEY"):
            self.config.ocr.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        if os.getenv("AWS_SESSION_TOKEN"):
            self.config.ocr.aws_session_token = os.getenv("AWS_SESSION_TOKEN")
        if os.getenv("AWS_DEFAULT_REGION"):
            self.config.ocr.aws_region = os.getenv("AWS_DEFAULT_REGION")

        if os.getenv("TESSERACT_CMD"):
            self.config.ocr.tesseract_cmd = os.getenv("TESSERACT_CMD")

        if os.getenv("AZURE_ENDPOINT"):
            self.config.ocr.azure_endpoint = os.getenv("AZURE_ENDPOINT")
        if os.getenv("AZURE_API_KEY"):
            self.config.ocr.azure_api_key = os.getenv("AZURE_API_KEY")

        if os.getenv("MISTRAL_API_KEY"):
            self.config.ocr.mistral_api_key = os.getenv("MISTRAL_API_KEY")


        if os.getenv("PDF_PROCESSOR_DEBUG"):
            self.config.debug = os.getenv("PDF_PROCESSOR_DEBUG").lower() == "true"
        if os.getenv("PDF_PROCESSOR_ENV"):
            self.config.environment = os.getenv("PDF_PROCESSOR_ENV")
        if os.getenv("PDF_PROCESSOR_LOG_LEVEL"):
            self.config.logging.level = os.getenv("PDF_PROCESSOR_LOG_LEVEL")

        if os.getenv("REDIS_HOST"):
            self.config.cache.redis_host = os.getenv("REDIS_HOST")
        if os.getenv("REDIS_PORT"):
            self.config.cache.redis_port = int(os.getenv("REDIS_PORT"))
    
    def _load_from_file(self, config_path: Path) -> None:
        try:
            with open(config_path, 'r') as f:
                file_config = json.load(f)
            
            self._merge_config(file_config)
            
        except json.JSONDecodeError as e:
            raise InvalidConfigurationError("config_file", str(e), "valid JSON")
        except Exception as e:
            raise ConfigurationError(f"Failed to load config from {config_path}: {e}")
    
    def _merge_config(self, file_config: Dict[str, Any]) -> None:

        if "ocr" in file_config:
            ocr_config = file_config["ocr"]
            for key, value in ocr_config.items():
                if hasattr(self.config.ocr, key):
                    setattr(self.config.ocr, key, value)

        if "processing" in file_config:
            proc_config = file_config["processing"]
            for key, value in proc_config.items():
                if hasattr(self.config.processing, key):
                    setattr(self.config.processing, key, value)

        if "evaluation" in file_config:
            eval_config = file_config["evaluation"]
            for key, value in eval_config.items():
                if hasattr(self.config.evaluation, key):
                    setattr(self.config.evaluation, key, value)

        if "export" in file_config:
            export_config = file_config["export"]
            for key, value in export_config.items():
                if hasattr(self.config.export, key):
                    setattr(self.config.export, key, value)

        if "logging" in file_config:
            log_config = file_config["logging"]
            for key, value in log_config.items():
                if hasattr(self.config.logging, key):
                    setattr(self.config.logging, key, value)

        for key in ["debug", "environment", "version"]:
            if key in file_config:
                setattr(self.config, key, file_config[key])
    
    def load_config(self, config_path: Optional[Path] = None) -> Dict[str, Any]:
        if config_path:
            self.config_path = config_path
            self._load_config()
        
        return self.to_dict()
    
    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        current = self.config
        
        try:
            for k in keys:
                current = getattr(current, k)
            return current
        except AttributeError:
            return default
    
    def set(self, key: str, value: Any) -> None:
        keys = key.split('.')
        current = self.config

        for k in keys[:-1]:
            if not hasattr(current, k):
                raise InvalidConfigurationError(key, value, "existing configuration path")
            current = getattr(current, k)

        final_key = keys[-1]
        if not hasattr(current, final_key):
            raise InvalidConfigurationError(key, value, "existing configuration key")
        
        setattr(current, final_key, value)
    
    def validate_config(self) -> bool:
        errors = []

        if not self.config.ocr.preferred_engine:
            errors.append("OCR preferred_engine is required")

        if self.config.ocr.preferred_engine in ["aws_textract", "claude_ocr"]:
            if not self.config.ocr.aws_access_key_id:
                errors.append("AWS access key ID is required for AWS services")
            if not self.config.ocr.aws_secret_access_key:
                errors.append("AWS secret access key is required for AWS services")

        if self.config.ocr.preferred_engine == "azure_ocr":
            if not self.config.ocr.azure_endpoint:
                errors.append("Azure endpoint is required for Azure OCR")
            if not self.config.ocr.azure_api_key:
                errors.append("Azure API key is required for Azure OCR")

        if not 0 <= self.config.ocr.confidence_threshold <= 1:
            errors.append("OCR confidence threshold must be between 0 and 1")
        
        if not 0 <= self.config.evaluation.iou_threshold_50 <= 1:
            errors.append("IoU threshold must be between 0 and 1")

        if self.config.logging.file_path:
            log_path = Path(self.config.logging.file_path)
            if not log_path.parent.exists():
                errors.append(f"Log directory does not exist: {log_path.parent}")

        if self.config.export.default_format not in self.config.export.supported_formats:
            errors.append("Default export format must be in supported formats")
        
        if errors:
            raise ConfigurationValidationError(errors, [])
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ocr": {
                "preferred_engine": self.config.ocr.preferred_engine,
                "fallback_engines": self.config.ocr.fallback_engines,
                "confidence_threshold": self.config.ocr.confidence_threshold,
                "timeout_seconds": self.config.ocr.timeout_seconds,
                "max_retries": self.config.ocr.max_retries,
                "aws_region": self.config.ocr.aws_region,
                "tesseract_configs": self.config.ocr.tesseract_configs
            },
            "processing": {
                "use_ocr": self.config.processing.use_ocr,
                "use_pdf_text": self.config.processing.use_pdf_text,
                "use_image_enhancement": self.config.processing.use_image_enhancement,
                "use_table_detection": self.config.processing.use_table_detection,
                "use_spatial_analysis": self.config.processing.use_spatial_analysis,
                "use_pattern_extraction": self.config.processing.use_pattern_extraction,
                "image_scale_factor": self.config.processing.image_scale_factor,
                "max_image_size": self.config.processing.max_image_size
            },
            "evaluation": {
                "calculate_cer": self.config.evaluation.calculate_cer,
                "calculate_wer": self.config.evaluation.calculate_wer,
                "calculate_bleu": self.config.evaluation.calculate_bleu,
                "excellent_cer_threshold": self.config.evaluation.excellent_cer_threshold,
                "excellent_wer_threshold": self.config.evaluation.excellent_wer_threshold
            },
            "export": {
                "default_format": self.config.export.default_format,
                "supported_formats": self.config.export.supported_formats,
                "output_directory": self.config.export.output_directory,
                "include_metadata": self.config.export.include_metadata
            },
            "logging": {
                "level": self.config.logging.level,
                "format": self.config.logging.format,
                "file_path": self.config.logging.file_path,
                "console_output": self.config.logging.console_output
            },
            "debug": self.config.debug,
            "environment": self.config.environment,
            "version": self.config.version
        }
    
    def save_config(self, output_path: Path) -> None:
        config_dict = self.to_dict()
        
        with open(output_path, 'w') as f:
            json.dump(config_dict, f, indent=2)
    
    def create_default_config(self, output_path: Path) -> None:
        default_config = ApplicationConfig()
        config_dict = {
            "ocr": {
                "preferred_engine": default_config.ocr.preferred_engine,
                "fallback_engines": default_config.ocr.fallback_engines,
                "confidence_threshold": default_config.ocr.confidence_threshold,
                "aws_region": default_config.ocr.aws_region
            },
            "processing": {
                "use_ocr": default_config.processing.use_ocr,
                "use_pdf_text": default_config.processing.use_pdf_text,
                "image_scale_factor": default_config.processing.image_scale_factor
            },
            "evaluation": {
                "calculate_cer": default_config.evaluation.calculate_cer,
                "calculate_wer": default_config.evaluation.calculate_wer,
                "excellent_cer_threshold": default_config.evaluation.excellent_cer_threshold
            },
            "export": {
                "default_format": default_config.export.default_format,
                "output_directory": default_config.export.output_directory
            },
            "logging": {
                "level": default_config.logging.level,
                "console_output": default_config.logging.console_output
            }
        }
        
        with open(output_path, 'w') as f:
            json.dump(config_dict, f, indent=2)


_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def initialize_config(config_path: Optional[Path] = None) -> ConfigManager:
    global _config_manager
    _config_manager = ConfigManager(config_path)
    return _config_manager


def reset_config() -> None:
    global _config_manager
    _config_manager = None
