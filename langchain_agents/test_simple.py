import asyncio
import sys
from pathlib import Path

# Add current directory to path
sys.path.append('.')

from workflow import process_pdf_with_agents


async def test_workflow():
    """Simple test of the multi-agent workflow"""

    # Look for any PDF in the parent directories
    search_paths = [
        "../",
        "../data/",
        "../data/prj_01/",
        "../data/prj_02/",
        "../../"
    ]

    pdf_path = None
    for search_path in search_paths:
        search_dir = Path(search_path)
        if search_dir.exists():
            # Find any PDF file
            pdf_files = list(search_dir.glob("**/*.pdf"))
            if pdf_files:
                pdf_path = str(pdf_files[0])
                break

    if not pdf_path:
        print("⚠️ No PDF files found in any search directory.")
        print("Search directories checked:")
        for path in search_paths:
            abs_path = Path(path).resolve()
            print(f"   - {abs_path} ({'exists' if abs_path.exists() else 'not found'})")

        print("\n💡 To test the system:")
        print("1. Place any PDF file in one of the above directories")
        print("2. Or update the pdf_path variable in this script")
        print("3. Or run with: python test_simple.py --pdf 'path/to/your/file.pdf'")
        return

    print(f"🧪 Testing multi-agent workflow with: {pdf_path}")
    print("=" * 60)

    try:
        result = await process_pdf_with_agents(
            pdf_path,
            prompt_engineering=True,
            optimization_level="balanced"
        )

        if result['success']:
            print("\n✅ Test completed successfully!")
            final_results = result['final_results']
            print(f"📊 Results saved to:")
            print(f"   📄 CSV: {final_results['csv_path']}")
            print(f"   📄 JSON: {final_results['json_path']}")

            summary = final_results['summary']
            print(f"\n📈 Summary:")
            print(f"   Questions answered: {summary['questions_answered']}/{summary['questions_total']}")
            print(f"   Defaults applied: {summary['defaults_applied']}")

        else:
            print(f"\n❌ Test failed: {result.get('error', 'Unknown error')}")
            if 'step_failed' in result:
                print(f"   Failed at step: {result['step_failed']}")

    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", help="Path to PDF file to test with")
    args = parser.parse_args()

    if args.pdf:
        # Override with user-provided PDF
        import asyncio


        async def test_with_user_pdf():
            result = await process_pdf_with_agents(args.pdf)
            print("Result:", result)


        asyncio.run(test_with_user_pdf())
    else:
        asyncio.run(test_workflow())