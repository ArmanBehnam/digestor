import os
import json
import csv
import openai
from llm_tools.config_loader import ConfigLoader
from llm_tools.ocr_processing import OCRProcessor
from llm_tools.keyword_filter import KeywordFilter
from llm_tools.llm_interface import LLMInterface
from llm_tools.result_writer import ResultWriter
from llm_tools.postprocessor import PostProcessor
from llm_tools.utils import run_pipeline_per_project


def apply_deflection_defaults(answers, questions, config):
    """
    Apply default deflection values for deflection-related questions if not found in OCR.
    """
    # Load deflection defaults
    deflection_defaults = {}
    try:
        with open("deflection_defaults.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                deflection_defaults[row['Question']] = row['DefaultAnswer']
        print(f"✅ Loaded {len(deflection_defaults)} deflection defaults")
        print(f"   Available defaults: {list(deflection_defaults.keys())}")
    except FileNotFoundError:
        print("Warning: deflection_defaults.csv not found. Skipping default application.")
        return answers

    # Debug: Print the incoming answers format
    print(f"📋 Processing {len(answers)} answers, Questions: {len(questions)}")
    if answers:
        first_key = list(answers.keys())[0]
        print(f"   Sample answer format: {first_key} -> {type(answers[first_key])}")

    # Process each answer
    processed_answers = {}
    defaults_applied = 0

    for i, question in enumerate(questions):
        qid = f"Q{i + 1}"
        print(f"\n🔍 Processing Q{i + 1}: {question[:50]}...")

        if qid in answers:
            answer_data = answers[qid]

            # Handle both old format (string) and new format (dict)
            if isinstance(answer_data, str):
                answer_text = answer_data
                page_info = None
                confidence = 50
            else:
                answer_text = answer_data.get('answer', 'Not Found')
                page_info = answer_data.get('page', None)
                confidence = answer_data.get('confidence', 0)

            print(f"   📄 Original answer: '{answer_text}'")

            # Check if this is a deflection question and answer was not found
            answer_not_found = answer_text.lower() in ['not found', 'nan', '', 'error'] or answer_text.startswith(
                'Error')
            question_has_default = question in deflection_defaults

            print(f"   🔍 Answer not found: {answer_not_found}")
            print(f"   🎯 Question has default: {question_has_default}")

            if answer_not_found and question_has_default:
                # Apply default value for deflection questions only
                processed_answers[qid] = {
                    'answer': deflection_defaults[question],
                    'page': 'Default',
                    'confidence': 95,
                    'source': 'deflection_defaults.csv'
                }
                defaults_applied += 1
                print(f"   ✅ APPLIED DEFAULT: {deflection_defaults[question]}")
            else:
                # Keep original answer - including "Not Found" for non-deflection questions
                processed_answers[qid] = {
                    'answer': answer_text if answer_text else 'Not Found',
                    'page': page_info,
                    'confidence': confidence,
                    'source': 'OCR' if not answer_not_found else 'Not Found in Document'
                }
                print(f"   ➡️ Kept original: '{answer_text}'")
        else:
            # No answer found at all
            print(f"   ❌ No answer data for {qid}")
            processed_answers[qid] = {
                'answer': 'Not Found',
                'page': None,
                'confidence': 0,
                'source': 'Missing'
            }

    print(f"\n🎯 DEFLECTION DEFAULTS SUMMARY: Applied {defaults_applied} defaults out of {len(questions)} questions")
    return processed_answers


def process_llm_with_utils(data_dir, config):
    """
    Process LLM using the optimized utils functions for per-project processing.
    """
    print("🤖 LLM PROCESSING MODE - Using Optimized Utils with Hierarchical Engines")
    print("=" * 60)

    # Run per-project processing with optimized utils
    results = run_pipeline_per_project(data_dir=data_dir, verbose=True)

    if results:
        stats = results['overall_stats']
        print(f"\n🎯 FINAL RESULTS: {results['overall_success_rate']:.1f}% overall success rate")
        print(f"🏗️ Projects: {stats['successful_projects']}/{stats['total_projects']} processed successfully")
        print(f"📊 {stats['total_answers']}/{stats['total_questions']} questions answered across all projects")
        print(f"💾 Results saved in respective project folders")

        # Optional: Show results by project
        if results['project_results']:
            print("\n🏆 RESULTS BY PROJECT:")
            for project_name, project_data in results['project_results'].items():
                metrics = project_data['metrics']
                print(f"\n📁 {project_name}:")
                print(
                    f"   ✅ {metrics['success_rate']:.1f}% success ({metrics['successful_answers']}/{metrics['total_questions']})")
                print(f"   📄 {len(project_data['combined_pages'])} pages processed")
                print(f"   💾 Results: {project_data['output_path']}")

        return True
    else:
        print("❌ No results generated")
        return False


def process_project(project_folder, config, questions, mode, llm):
    all_results = []
    ocr = OCRProcessor(config)
    pdf_files = [os.path.join(project_folder, f) for f in os.listdir(project_folder) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print(f"No PDFs found in {project_folder}")
        return []
    target_keywords = ocr.processor._get_target_keywords()
    category_keywords = [kw for kws in config['category_keywords'].values() for kw in kws]
    for pdf_file in pdf_files:
        print(f"Processing: {pdf_file}")
        output_json = os.path.splitext(pdf_file)[0] + "_ocr_result.json"
        if mode in ["ocr", "both"]:
            result = ocr.process_pdf(pdf_file)
            page_results = result.get('page_level_results', [])
            filtered_pages = KeywordFilter.filter_pages(
                page_results,
                target_keywords,
                config['custom_keywords'],
                category_keywords,
                category_threshold=config.get('CATEGORY_THRESHOLD', 2),
                fuzzy_flag=True
            )
            new_result = {
                'document_info': result['document_info'],
                'filtered_pages_only': filtered_pages
            }
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(new_result, f, indent=2, ensure_ascii=False, default=str)
        if mode in ["llm", "both"]:
            if not os.path.exists(output_json):
                print(f"OCR output not found for {pdf_file}. Run OCR first.")
                continue
            with open(output_json, "r", encoding="utf-8") as f:
                result = json.load(f)
            for page in result.get('filtered_pages_only', []):
                answers = llm.answer_page(page.get('extracted_text', ''), questions)

                # Process answers and apply deflection defaults if needed
                processed_answers = apply_deflection_defaults(answers, questions, config)

                all_results.append({
                    'project': os.path.basename(project_folder),
                    'pdf': os.path.basename(pdf_file),
                    'page': page.get('page_number', 'nan'),
                    'answers': processed_answers
                })
    return all_results


def main():
    try:
        config = ConfigLoader.load("llm_tools/config.yaml")
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # Set AWS environment variables if they exist in config
    if 'AWS_ACCESS_KEY_ID' in config:
        os.environ["AWS_ACCESS_KEY_ID"] = config['AWS_ACCESS_KEY_ID']
    if 'AWS_SECRET_ACCESS_KEY' in config:
        os.environ["AWS_SECRET_ACCESS_KEY"] = config['AWS_SECRET_ACCESS_KEY']
    if 'AWS_DEFAULT_REGION' in config:
        os.environ["AWS_DEFAULT_REGION"] = config['AWS_DEFAULT_REGION']

    # Set Azure environment variables for ocr_tools
    if 'AZURE_ENDPOINT' in config:
        os.environ["AZURE_ENDPOINT"] = config['AZURE_ENDPOINT']
    if 'AZURE_API_KEY' in config:
        os.environ["AZURE_API_KEY"] = config['AZURE_API_KEY']

    data_dir = input("Enter the main data directory: ").strip().strip('"\'')

    # Validate data directory exists
    if not os.path.exists(data_dir):
        print(f"Error: Directory '{data_dir}' does not exist.")
        return

    if not os.path.isdir(data_dir):
        print(f"Error: '{data_dir}' is not a directory.")
        return

    print("Select mode:")
    print("1. OCR only (generate *_result.json for each PDF)")
    print("2. LLM only (use optimized utils for per-project processing)")
    print("3. Both (run OCR and then LLM Q&A)")
    mode_choice = input("Enter choice (1/2/3): ").strip()
    if mode_choice == "1":
        mode = "ocr"
    elif mode_choice == "2":
        mode = "llm"
    else:
        mode = "both"
    print(f"Running in {mode} mode...")

    # Ask about prompt engineering for LLM-related modes
    if mode in ["llm", "both"]:
        print("\n🔧 PROMPT ENGINEERING OPTIONS:")
        print("=" * 35)
        print("Prompt engineering can optimize prompts based on document context")
        print("for better accuracy and confidence in engineering document analysis.")
        print()
        print("1. Automatic Prompt Engineering (RECOMMENDED)")
        print("   ✅ Context-aware optimization")
        print("   ✅ Domain-specific enhancements")
        print("   ✅ Better accuracy for technical content")
        print("   ✅ OCR error resilience")
        print()
        print("2. Static Prompts (Traditional)")
        print("   ⚡ Faster processing")
        print("   📝 Standard generic prompts")
        print("   🔧 Simple and predictable")
        print()

        prompt_choice = input("Choose prompt type (1=Automatic, 2=Static) [1]: ").strip()

        if prompt_choice == "2":
            config['prompt_engineering']['enabled'] = False
            print("📝 Using static prompts (traditional mode)")
        else:
            config['prompt_engineering']['enabled'] = True
            print("🔧 Using automatic prompt engineering (optimized mode)")

            # Optional: Ask for optimization level
            print("\nOptimization level:")
            print("1. Conservative (fast, minimal optimization)")
            print("2. Balanced (recommended, good performance/quality)")
            print("3. Aggressive (maximum optimization, slower)")

            level_choice = input("Choose level (1/2/3) [2]: ").strip()
            if level_choice == "1":
                config['prompt_engineering']['optimization_level'] = "conservative"
                print("⚡ Using conservative optimization")
            elif level_choice == "3":
                config['prompt_engineering']['optimization_level'] = "aggressive"
                print("🚀 Using aggressive optimization")
            else:
                config['prompt_engineering']['optimization_level'] = "balanced"
                print("⚖️ Using balanced optimization")

        print()  # Add spacing before next section

    # Handle LLM-only mode with optimized utils
    if mode == "llm":
        # Initialize and show LLM engine status
        try:
            llm_test = LLMInterface(config)
            print("\n🤖 LLM ENGINES STATUS:")
            engine_stats = llm_test.get_engine_stats()
            for stat in engine_stats:
                status = "🟢 Available" if stat['is_available'] else "🔴 Unavailable"
                print(f"   • {stat['engine_name']} (Priority: {stat['priority']}) - {status}")
                if stat['last_error']:
                    print(f"     ⚠️ Last Error: {stat['last_error']}")

            # Show prompt engineering status
            print("\n🔧 PROMPT ENGINEERING STATUS:")
            pe_stats = llm_test.prompt_engineer.get_optimization_stats()
            pe_enabled = pe_stats.get('enabled', False)
            pe_level = pe_stats.get('optimization_level', 'unknown')
            pe_status = "🟢 ENABLED" if pe_enabled else "🔴 DISABLED"
            print(f"   • Status: {pe_status}")
            if pe_enabled:
                print(f"   • Optimization Level: {pe_level.title()}")
                print(f"   • Cached Prompts: {pe_stats.get('cached_prompts', 0)}")
                print("   • Features: Context analysis, domain adaptation, error handling")
            else:
                print("   • Using static prompts (traditional mode)")
            print()
        except Exception as e:
            print(f"⚠️ Could not get LLM engine status: {e}")

        success = process_llm_with_utils(data_dir, config)
        if success:
            print("\n✅ LLM processing completed successfully!")
        else:
            print("\n❌ LLM processing failed!")
        return

    # Handle "both" mode - check if JSON files exist, skip OCR if they do
    if mode == "both":
        # Check if JSON files already exist for all projects
        json_files_exist = True
        projects_with_json = []
        projects_without_json = []

        for project in os.listdir(data_dir):
            project_folder = os.path.join(data_dir, project)
            if os.path.isdir(project_folder):
                pdf_files = [f for f in os.listdir(project_folder) if f.lower().endswith('.pdf')]
                json_files = [f for f in os.listdir(project_folder) if f.endswith('_ocr_result.json')]

                if pdf_files and json_files:
                    projects_with_json.append(project)
                elif pdf_files:
                    projects_without_json.append(project)
                    json_files_exist = False

        if projects_without_json:
            print(f"\n🔧 PHASE 1: OCR PROCESSING")
            print("=" * 40)
            print(f"📁 Found {len(projects_without_json)} projects needing OCR processing:")
            for proj in projects_without_json:
                print(f"   • {proj}")

            # Run OCR processing only for projects that need it
            questions = config['questions']
            all_results = []

            for project in projects_without_json:
                project_folder = os.path.join(data_dir, project)
                print(f"🔍 OCR Processing {project_folder} ...")
                try:
                    # Only run OCR part
                    results = process_project(project_folder, config, questions, "ocr", None)
                    all_results.extend(results)
                except Exception as e:
                    print(f"❌ Error during OCR processing for project {project_folder}: {e}")
                    continue

            print(f"\n✅ OCR processing completed for {len(projects_without_json)} projects.")
        else:
            print(f"\n✅ SKIPPING OCR: All {len(projects_with_json)} projects already have JSON files")
            for proj in projects_with_json:
                print(f"   • {proj}")

        print("\n🤖 PHASE 2: LLM PROCESSING")
        print("=" * 40)

        # Show LLM engine and prompt engineering status before processing
        try:
            llm_test = LLMInterface(config)
            print("🤖 LLM ENGINES STATUS:")
            engine_stats = llm_test.get_engine_stats()
            for stat in engine_stats:
                status = "🟢 Available" if stat['is_available'] else "🔴 Unavailable"
                print(f"   • {stat['engine_name']} (Priority: {stat['priority']}) - {status}")
                if stat['last_error']:
                    print(f"     ⚠️ Last Error: {stat['last_error']}")

            # Show prompt engineering status
            print("\n🔧 PROMPT ENGINEERING STATUS:")
            pe_stats = llm_test.prompt_engineer.get_optimization_stats()
            pe_enabled = pe_stats.get('enabled', False)
            pe_level = pe_stats.get('optimization_level', 'unknown')
            pe_status = "🟢 ENABLED" if pe_enabled else "🔴 DISABLED"
            print(f"   • Status: {pe_status}")
            if pe_enabled:
                print(f"   • Optimization Level: {pe_level.title()}")
                print(f"   • Cached Prompts: {pe_stats.get('cached_prompts', 0)}")
                print("   • Features: Context analysis, domain adaptation, error handling")
            else:
                print("   • Using static prompts (traditional mode)")
            print()
        except Exception as e:
            print(f"⚠️ Could not get LLM status: {e}")

        # Now run LLM processing with optimized utils
        success = process_llm_with_utils(data_dir, config)
        if success:
            print("\n✅ Both OCR and LLM processing completed successfully!")
        else:
            print("\n❌ LLM processing failed!")
        return

    # Validate required config keys for OCR mode
    if 'questions' not in config:
        print("Error: 'questions' not found in config.")
        return

    questions = config['questions']
    all_results = []

    # Process OCR mode only (both mode is handled above)
    for project in os.listdir(data_dir):
        project_folder = os.path.join(data_dir, project)
        if os.path.isdir(project_folder):
            print(f"🔍 OCR Processing {project_folder} ...")
            try:
                results = process_project(project_folder, config, questions, mode, None)
                all_results.extend(results)
            except Exception as e:
                print(f"❌ Error processing project {project_folder}: {e}")
                continue

    print(f"✅ OCR processing completed. Total results: {len(all_results)}")


if __name__ == "__main__":
    main()