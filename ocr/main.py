# ocr/main.py

import os
import sys
import time
from pathlib import Path
import json

from ocr.utils.help import PDFProcessor, Phase1PDFProcessor, normalize_input_to_pdf


class MenuInterface:
    def __init__(self):
        self.processor = None
        self.enhanced_processor = None
        self.current_pdf = None

    def display_banner(self):
        print("\n" + "="*60)
        print("           CDE OCR v2.1")
        print("           Let's Begin")
        print("="*60)

    def display_main_menu(self):
        print("\nMAIN MENU")
        print("─" * 40)
        print("1. Upload/Select PDF File")
        print("2. Full Document Processing")
        print("3. Phase 1 Processing")
        print("4. OCR Text Extraction Only")
        print("5. Table Extraction Only")
        print("6. Pattern Extraction Only")
        print("7. Test Azure OCR")
        print("8. Test Claude OCR")
        print("9. Batch Processing")
        print("10. System Information")
        print("11. Validate Configuration")
        print("12. Exit")
        print("─" * 40)

    def get_user_choice(self, prompt="Enter your choice: ", max_choice=10):
        while True:
            try:
                user_input = input(prompt).strip()
                choice = int(user_input)
                if 1 <= choice <= max_choice:
                    return choice
                else:
                    print(f"Please enter a number between 1 and {max_choice}")
            except ValueError:
                if user_input.endswith('.pdf') and ('\\' in user_input or '/' in user_input):
                    print("💡 It looks like you entered a file path. Please select option 1 first, then enter the path.")
                else:
                    print("Please enter a valid number")

    def select_pdf_file(self):
        print("\nFile Selection (PDF/DWG)")
        print("─" * 40)
        print("1. Enter file path manually")
        print("2. Browse current directory")
        print("3. Go back to main menu")

        choice = self.get_user_choice("Select option: ", max_choice=3)

        if choice == 1:
            file_path = input("Enter PDF/DWG file path: ").strip().strip('"\'')
            if os.path.exists(file_path) and (file_path.lower().endswith('.pdf') or file_path.lower().endswith('.dwg')):
                self.current_pdf = normalize_input_to_pdf(Path(file_path))
                print(f"Selected: {self.current_pdf.name}")
                return True
            else:
                print("File not found or not a PDF/DWG file")
                return False

        elif choice == 2:
            current_dir = Path.cwd()
            files = list(current_dir.glob("*.pdf")) + list(current_dir.glob("*.dwg"))

            if not files:
                print("No PDF/DWG files found in current directory")
                return False

            print(f"\nFiles in {current_dir}:")
            for i, f in enumerate(files, 1):
                print(f"{i}. {f.name}")

            if len(files) == 1:
                file_choice = 1
            else:
                file_choice = self.get_user_choice("Select file: ", len(files))

            self.current_pdf = normalize_input_to_pdf(files[file_choice - 1])
            print(f"Selected: {self.current_pdf.name}")
            return True

        return False

    def initialize_processor(self):
        if self.processor is None:
            print("Initializing PDF Processor")
            try:
                self.processor = PDFProcessor()
                print("Processor initialized successfully")
                return True
            except Exception as e:
                print(f"Failed to initialize processor: {e}")
                return False
        return True

    def initialize_enhanced_processor(self):
        if self.enhanced_processor is None:
            print("Initializing PDF Processor")
            try:
                self.enhanced_processor = Phase1PDFProcessor()
                print("Processor initialized successfully")
                return True
            except Exception as e:
                print(f"Failed to initialize processor: {e}")
                return False
        return True

    def check_pdf_selected(self):
        if self.current_pdf is None:
            print("No PDF file selected. Please select a file first.")
            return False
        return True

    def full_processing(self):
        if not self.check_pdf_selected() or not self.initialize_processor():
            return

        print(f"\nFull Processing: {self.current_pdf.name}")
        print("─" * 50)

        print("Processing Options:")
        use_ocr = input("Enable OCR? (Y/n): ").strip().lower() != 'n'
        extract_tables = input("Extract tables? (Y/n): ").strip().lower() != 'n'
        extract_patterns = input("Extract patterns? (Y/n): ").strip().lower() != 'n'
        enhance_images = input("Enhance images? (Y/n): ").strip().lower() != 'n'

        try:
            print("\nProcessing document")
            start_time = time.time()

            result = self.processor.process(
                self.current_pdf,
                use_ocr=use_ocr,
                extract_tables=extract_tables,
                extract_patterns=extract_patterns,
                enhance_images=enhance_images
            )

            elapsed_time = time.time() - start_time

            print(f"\nProcessing Complete ({elapsed_time:.2f}s)")
            print("─" * 50)
            print(f"Confidence: {result.confidence:.2f}")
            print(f"Pages: {result.total_pages}")
            print(f"Text Elements: {len(result.elements)}")
            print(f"Tables: {len(result.tables)}")
            print(f"Pattern Categories: {len(result.structured_data)}")

            if result.structured_data:
                print(f"\nStructured Data Found:")
                try:
                    for category, items in result.structured_data.items():
                        if hasattr(items, '__len__'):
                            print(f"  • {category}: {len(items)} items")
                        else:
                            print(f"  • {category}: {items}")
                except Exception as display_error:
                    print(f"Error displaying structured data: {display_error}")

            try:
                output_file = self.current_pdf.parent / f"{self.current_pdf.stem}_result.json"
                self.processor.save_result(result, output_file)
                print(f"Results saved to: {output_file.name}")
            except Exception as save_error:
                print(f"Warning: Could not save result file: {save_error}")
                print("Processing completed successfully (save failed)")

        except Exception as e:
            print(f"Processing failed: {e}")

    def enhanced_processing(self):
        if not self.check_pdf_selected() or not self.initialize_enhanced_processor():
            return

        print(f"\nPhase 1 Processing: {self.current_pdf.name}")
        print("─" * 50)

        use_ocr = input("Enable OCR? (Y/n): ").strip().lower() != 'n'
        extract_tables = input("Extract tables? (Y/n): ").strip().lower() != 'n'
        extract_patterns = input("Extract patterns? (Y/n): ").strip().lower() != 'n'
        enhance_images = input("Enhance images? (Y/n): ").strip().lower() != 'n'

        # Custom keywords option
        add_custom = input("Add custom keywords? (Y/n): ").strip().lower() == 'y'
        if add_custom:
            custom_keywords_input = input("Enter keywords (comma-separated): ").strip()
            if custom_keywords_input:
                custom_keywords = [kw.strip() for kw in custom_keywords_input.split(',')]
                self.enhanced_processor.add_custom_keywords(custom_keywords)
                print(f"Added {len(custom_keywords)} custom keywords")

        try:
            print("\nProcessing document with enhanced features")
            start_time = time.time()

            enhanced_result = self.enhanced_processor.process_with_page_results(
                self.current_pdf,
                use_ocr=use_ocr,
                extract_tables=extract_tables,
                extract_patterns=extract_patterns,
                enhance_images=enhance_images
            )

            elapsed_time = time.time() - start_time

            print(f"\nProcessing Completed ({elapsed_time:.2f}s)")
            print("─" * 50)

            doc_info = enhanced_result['document_info']
            print(f"Document: {doc_info['filename']}")
            print(f"Total Pages: {doc_info['total_pages']}")
            print(f"Overall Confidence: {doc_info['confidence']:.2f}")
            print(f"Document Type: {doc_info['document_type']}")

            filtered_info = enhanced_result['filtered_pages']
            print(f"\nRESULTS:")
            print(f"Pages with target keywords: {filtered_info['total_matching_pages']}")
            print(f"Keywords found: {', '.join(filtered_info['keywords_found'])}")

            if filtered_info['matching_pages']:
                page_numbers = [str(page['page_number']) for page in filtered_info['matching_pages']]
                print(f"Matching page numbers: {', '.join(page_numbers)}")

                summary = self.enhanced_processor.get_page_summary(enhanced_result)
                print(f"Percentage with keywords: {summary['percentage_with_keywords']:.1f}%")

            try:
                output_file = self.current_pdf.parent / f"{self.current_pdf.stem}_result.json"
                new_result = {
                    'document_info': enhanced_result['document_info'],
                    'filtered_pages_only': []
                }
                for page in enhanced_result['filtered_pages']['matching_pages']:
                    minimal_page = {
                        'page_number': page['page_number'],
                        'extracted_text': page['extracted_text'],
                        'matched_keywords': page.get('matched_keywords', []),
                        'confidence_avg': page['confidence_avg'],
                        'element_count': page['element_count'],
                        'is_fallback': page.get('fallback_extraction', False)
                    }
                    new_result['filtered_pages_only'].append(minimal_page)
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(new_result, f, indent=2, ensure_ascii=False, default=str)
                print(f"\nresults saved to: {output_file.name}")

            except Exception as save_error:
                print(f"Warning: Could not save result files: {save_error}")

        except Exception as e:
            print(f"processing failed: {e}")

    def ocr_only(self):
        if not self.check_pdf_selected() or not self.initialize_processor():
            return

        print(f"\nOCR Extraction: {self.current_pdf.name}")
        print("─" * 50)

        try:
            print("Extracting text with OCR")
            result = self.processor.process(
                self.current_pdf,
                use_ocr=True,
                extract_tables=False,
                extract_patterns=False
            )

            print(f"\nOCR Completed")
            print("─" * 30)
            print(f"Text Elements: {len(result.elements)}")
            print(f"Text Length: {len(result.extracted_text)} characters")

            if result.extracted_text:
                preview = result.extracted_text[:500]
                print(f"\nText Preview:")
                print(f"{preview}{'...' if len(result.extracted_text) > 500 else ''}")

        except Exception as e:
            print(f"OCR failed: {e}")

    def table_extraction_only(self):
        if not self.check_pdf_selected() or not self.initialize_processor():
            return

        print(f"\nTable Extraction: {self.current_pdf.name}")
        print("─" * 50)

        try:
            print("Extracting tables")
            result = self.processor.process(
                self.current_pdf,
                use_ocr=True,
                extract_tables=True,
                extract_patterns=False
            )

            print(f"\nTable Extraction Completed")
            print("─" * 35)
            print(f"Tables Found: {len(result.tables)}")

            if result.tables:
                for i, table in enumerate(result.tables, 1):
                    print(f"  Table {i}: {len(table.get('rows', []))} rows x {len(table.get('rows', [[]])[0]) if table.get('rows') else 0} columns")

        except Exception as e:
            print(f"Table extraction failed: {e}")

    def pattern_extraction_only(self):
        if not self.check_pdf_selected() or not self.initialize_processor():
            return

        print(f"\nPattern Extraction: {self.current_pdf.name}")
        print("─" * 50)

        try:
            print("Extracting patterns")
            result = self.processor.process(
                self.current_pdf,
                use_ocr=False,
                extract_tables=False,
                extract_patterns=True
            )

            print(f"\nPattern Extraction Completed")
            print("─" * 40)
            print(f"Categories Found: {len(result.structured_data)}")

            if result.structured_data:
                for category, items in result.structured_data.items():
                    print(f"  • {category}: {items}")

        except Exception as e:
            print(f"Pattern extraction failed: {e}")

    def test_azure_ocr(self):
        if not self.check_pdf_selected() or not self.initialize_processor():
            return

        print(f"\nTesting Azure OCR: {self.current_pdf.name}")
        print("─" * 50)

        try:
            start_time = time.time()
            result = self.processor.process(
                self.current_pdf,
                use_ocr=True,
                ocr_engine="azure_ocr"
            )
            elapsed_time = time.time() - start_time

            print(f"\nAzure OCR Results ({elapsed_time:.2f}s)")
            print("─" * 40)
            print(f"Confidence: {result.confidence:.2f}")
            print(f"Text Elements: {len(result.elements)}")
            print(f"Text Length: {len(result.extracted_text)}")

            if result.extracted_text:
                preview = result.extracted_text[:300]
                print(f"\nText Preview:\n{preview}")

            try:
                output_file = self.current_pdf.parent / f"{self.current_pdf.stem}_azure_result.json"
                self.processor.save_result(result, output_file)
                print(f"\nAzure results saved to: {output_file.name}")
            except Exception as save_error:
                print(f"Warning: Could not save Azure result: {save_error}")

        except Exception as e:
            print(f"Azure OCR failed: {e}")

    def test_claude_ocr(self):
        if not self.check_pdf_selected() or not self.initialize_processor():
            return

        print(f"\nTesting Claude OCR: {self.current_pdf.name}")
        print("─" * 50)

        try:
            start_time = time.time()
            result = self.processor.process(
                self.current_pdf,
                use_ocr=True,
                ocr_engine="claude_ocr"
            )
            elapsed_time = time.time() - start_time

            print(f"\nClaude OCR Results ({elapsed_time:.2f}s)")
            print("─" * 40)
            print(f"Confidence: {result.confidence:.2f}")
            print(f"Text Elements: {len(result.elements)}")
            print(f"Text Length: {len(result.extracted_text)}")

            if result.extracted_text:
                preview = result.extracted_text[:300]
                print(f"\nText Preview:\n{preview}")

            try:
                output_file = self.current_pdf.parent / f"{self.current_pdf.stem}_claude_result.json"
                self.processor.save_result(result, output_file)
                print(f"\nClaude results saved to: {output_file.name}")
            except Exception as save_error:
                print(f"Warning: Could not save Claude result: {save_error}")

        except Exception as e:
            print(f"Claude OCR failed: {e}")


    def batch_processing(self):
        print("\nBatch Processing")
        print("─" * 40)

        input_dir = input("Enter input directory path: ").strip().strip('"\'')
        if not os.path.exists(input_dir):
            print("Input directory not found")
            return

        output_dir = input("Enter output directory path: ").strip().strip('"\'')

        if not self.initialize_processor():
            return

        try:
            print("Starting batch processing")
            results = self.processor.process_batch(Path(input_dir), Path(output_dir))

            print(f"\nBatch Processing Completed")
            print("─" * 40)
            print(f"Total Files: {results['total_files']}")
            print(f"Successful: {results['successful']}")
            print(f"Failed: {results['failed']}")

            if results['errors']:
                print(f"\nErrors:")
                for error in results['errors']:
                    print(f"  • {error['file']}: {error['error']}")

        except Exception as e:
            print(f"Batch processing failed: {e}")

    def show_system_info(self):
        if not self.initialize_processor():
            return

        print("\nSystem Information")
        print("─" * 50)

        info = self.processor.get_system_info()

        print(f"Processor Version: {info['processor_version']}")
        print(f"\nOCR Engines:")
        for name, engine_info in info['ocr_engines'].items():
            status = "Available" if engine_info['available'] else "Unavailable"
            print(f"  • {name}: {status} (Priority: {engine_info['priority']})")

        print(f"\nProcessing Stages:")
        for stage in info['available_stages']:
            print(f"  • {stage}")

        print(f"\nComponents:")
        for component, status in info['component_status'].items():
            status_icon = "Yes" if status else "No"
            print(f"  • {component}: {status_icon}")

    def validate_configuration(self):
        if not self.initialize_processor():
            return

        print("\nConfiguration Validation")
        print("─" * 50)

        try:
            validation = self.processor.validate_configuration()

            if validation['config_valid']:
                print("Configuration is valid")
            else:
                print("Configuration issues found:")
                for issue in validation['config_issues']:
                    print(f"  • {issue}")

            if validation['ocr_issues']:
                print(f"\nOCR Engine Issues:")
                for engine, issues in validation['ocr_issues'].items():
                    print(f"  • {engine}:")
                    for issue in issues:
                        print(f"    - {issue}")

            if validation['recommendations']:
                print(f"\n💡 Recommendations:")
                for rec in validation['recommendations']:
                    print(f"  • {rec}")

        except Exception as e:
            print(f"Validation failed: {e}")

    def run(self):
        self.display_banner()

        while True:
            self.display_main_menu()

            if self.current_pdf:
                print(f"Current PDF: {self.current_pdf.name}")
            else:
                print("No PDF selected")

            choice = self.get_user_choice()

            if choice == 1:
                self.select_pdf_file()
            elif choice == 2:
                self.full_processing()
            elif choice == 3:
                self.enhanced_processing()
            elif choice == 4:
                self.ocr_only()
            elif choice == 5:
                self.table_extraction_only()
            elif choice == 6:
                self.pattern_extraction_only()
            elif choice == 7:
                self.test_azure_ocr()
            elif choice == 8:
                self.test_claude_ocr()
            elif choice == 9:
                self.batch_processing()
            elif choice == 10:
                self.show_system_info()
            elif choice == 11:
                self.validate_configuration()
            elif choice == 12:  # Changed from 10
                print("\nThank you for your attention to this matter!")
                sys.exit(0)

            input("\nPress Enter to continue")

if __name__ == "__main__":
    interface = MenuInterface()
    interface.run()