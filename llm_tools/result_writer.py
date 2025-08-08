import csv
import os

class ResultWriter:
    @staticmethod
    def write_results_csv(project_folder, project_results, questions):
        csv_path = os.path.join(project_folder, "results.csv")
        with open(csv_path, "w", newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Project', 'PDF', 'Page', 'Question', 'Answer', 'Source_Page', 'Confidence', 'Source'])
            for result in project_results:
                # Iterate through questions in config file order to maintain consistent CSV structure
                for i, q in enumerate(questions):
                    qid = f'Q{i+1}'
                    answer_data = result['answers'].get(qid, {})
                    
                    # Handle both old format (string) and new format (dict)
                    if isinstance(answer_data, str):
                        answer = answer_data
                        source_page = 'N/A'
                        confidence = 'N/A'
                        source = 'Legacy'
                    else:
                        answer = answer_data.get('answer', 'Not Found')
                        source_page = answer_data.get('page', 'N/A')
                        confidence = answer_data.get('confidence', 0)
                        source = answer_data.get('source', 'OCR')
                    
                    writer.writerow([
                        result['project'], 
                        result['pdf'], 
                        result['page'], 
                        q, 
                        answer,
                        source_page,
                        f"{confidence}%",
                        source
                    ])
        print(f"Enhanced results saved to {csv_path}")
        print(f"Results include: Answer, Source Page, Confidence, and Data Source")