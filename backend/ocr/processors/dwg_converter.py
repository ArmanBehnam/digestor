# ocr/processors/dwg_converter.py

from pathlib import Path
import shutil
import tempfile
import os
from typing import Optional

from ocr.utils.help import _convert_dwg_to_pdf


class DWGConverter:
    @staticmethod
    def is_dwg(path: Path) -> bool:
        return path.suffix.lower() == ".dwg"

    @staticmethod
    def find_oda_converter() -> Optional[str]:
        env_p = os.environ.get("ODA_CONVERTER")
        if env_p and Path(env_p).exists():
            return env_p
        p = shutil.which("ODAFileConverter") or shutil.which("ODAFileConverter.exe")
        if p:
            return p
        default = Path(r"C:\Program Files\ODA\ODAFileConverter 26.7.0\ODAFileConverter.exe")
        if default.exists():
            return str(default)
        return None

    @staticmethod
    def convert_to_pdf(dwg_path: Path) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="dwg2pdf_"))
        return _convert_dwg_to_pdf(dwg_path, tmp_dir)
