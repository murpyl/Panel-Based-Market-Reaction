import pandas as pd
from pathlib import Path
from datetime import datetime

def count_rows_by_mont(folder_path):
    directory = Path(folder_path)
    csv = list(directory.glob('*.csv'))

    for file in csv:
        print(file)
        
        df = pd.read_csv(file, usecols = ['created_at_utc'])
        df['created_at_utc'] = pd.to_datetime(df['created_at_utc'], utc=True, errors='coerce')
        df['month'] = df['created_at_utc'].dt.tz_localize(None)
        df['month'] = df['created_at_utc'].dt.to_period('M')
        counts = df['month'].value_counts().sort_index()
        for month, count in counts.items():
            print(f'{month}: {count}')

count_rows_by_mont('x_posts')