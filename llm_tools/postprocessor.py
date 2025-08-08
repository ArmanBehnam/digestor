import pandas as pd
import os

class PostProcessor:
    @staticmethod
    def add_deflection_defaults(df, deflection_defaults_csv, project_folder):
        deflection_defaults = pd.read_csv(deflection_defaults_csv)
        deflection_map = dict(zip(deflection_defaults['Question'], deflection_defaults['DefaultAnswer']))
        deflection_questions = list(deflection_map.keys())
        new_rows = []
        for q in deflection_questions:
            if df[(df['Question'] == q) & (df['Answer'].str.lower() != 'nan')].empty:
                new_rows.append({
                    'Project': os.path.basename(project_folder),
                    'PDF': 'default',
                    'Page': 'default',
                    'Question': q,
                    'Answer': deflection_map[q]
                })
        if new_rows:
            df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        return df

    @staticmethod
    def remove_nan_rows(df):
        return df[df['Answer'].str.lower() != 'nan']

    @staticmethod
    def merge_results(df, project_folder):
        merged = []
        for q in df['Question'].unique():
            answers_df = df[df['Question'] == q][['Answer', 'PDF', 'Page']]
            answer_counts = answers_df['Answer'].value_counts()
            max_count = answer_counts.max()
            top_answers = answer_counts[answer_counts == max_count].index.tolist()
            if len(top_answers) == 1:
                ans = top_answers[0]
                row = answers_df[answers_df['Answer'] == ans].iloc[0]
                merged.append({
                    'Question': q,
                    'MergedAnswer': ans,
                    'PDF': row['PDF'],
                    'Page': row['Page']
                })
            else:
                for ans in top_answers:
                    row = answers_df[answers_df['Answer'] == ans].iloc[0]
                    merged.append({
                        'Question': q,
                        'MergedAnswer': ans,
                        'PDF': row['PDF'],
                        'Page': row['Page']
                    })
        merged_df = pd.DataFrame(merged)
        merged_path = os.path.join(project_folder, "merged_result.csv")
        merged_df.to_csv(merged_path, index=False)
        print(f"Merged results saved to {merged_path}")

    @staticmethod
    def postprocess(project_folder, deflection_defaults_csv):
        results_path = os.path.join(project_folder, "results.csv")
        if not os.path.exists(results_path):
            print(f"No results.csv found in {project_folder}")
            return
        df = pd.read_csv(results_path)
        df = PostProcessor.add_deflection_defaults(df, deflection_defaults_csv, project_folder)
        df = PostProcessor.remove_nan_rows(df)
        PostProcessor.merge_results(df, project_folder)