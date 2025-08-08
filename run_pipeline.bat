@echo off
echo ========================================
echo Talk2Drawings Pipeline - Final Version
echo ========================================
echo.
echo Make sure you have:
echo 1. Python 3.8+ installed
echo 2. API keys configured in llm_tools/config.yaml
echo 3. Data folder with PDF files ready
echo.
pause
python pipeline.py
pause
