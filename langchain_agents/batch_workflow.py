import asyncio
import argparse
from pathlib import Path
from workflow import Talk2DrawingsWorkflow

import os
os.environ.setdefault("AZURE_ENDPOINT", "https://ocr-document-cde.cognitiveservices.azure.com/")
os.environ.setdefault("AZURE_API_KEY", "1YOi3XppiUJNkPqimlGKtVsybyr3vxaZOZyQ353oOXt5OxA32fHVJQQJ99BGACYeBjFXJ3w3AAALACOG4WOR")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "AKIA3U3RKYD6JK4EUIGC")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "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")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

async def process_directory(directory_path, prompt_engineering=True):
    dir_path = Path(directory_path)
    pdf_files = list(dir_path.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in: {directory_path}")
        return []

    print(f"Found {len(pdf_files)} PDF files in directory")
    for pdf in pdf_files:
        print(f"   • {pdf.name}")

    workflow = Talk2DrawingsWorkflow()
    results = []

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"\nProcessing PDF {i}/{len(pdf_files)}: {pdf_path.name}")

        try:
            result = await workflow.process_document(str(pdf_path), prompt_engineering)
            results.append({
                'pdf_path': str(pdf_path),
                'result': result,
                'success': result['success']
            })

            if result['success']:
                print(f"Success: {pdf_path.name}")
            else:
                print(f"Failed: {pdf_path.name} - {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"Error: {pdf_path.name} - {e}")
            results.append({
                'pdf_path': str(pdf_path),
                'result': {'success': False, 'error': str(e)},
                'success': False
            })

        await asyncio.sleep(1)

    successful = len([r for r in results if r['success']])
    print(f"\nBatch summary: {successful}/{len(pdf_files)} PDFs processed successfully")

    return results


async def main():
    parser = argparse.ArgumentParser(description="Batch process PDFs with multi-agent system")
    parser.add_argument("--directory", required=True, help="Directory containing PDF files")
    parser.add_argument("--prompt-engineering", action="store_true", default=True)

    args = parser.parse_args()

    await process_directory(args.directory, args.prompt_engineering)


if __name__ == "__main__":
    asyncio.run(main())