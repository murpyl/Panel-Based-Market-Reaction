import pandas as pd
import glob
import os

HANDLE_MAP = {
    "satyanadella": "MSFT",
    "levie": "BOX",
    "cristianoamon": "QCOM",
    "vladtenev": "HOOD",
    "tobi": "SHOP",
    "Benioff": "CRM",
}


def combine_ticker_csvs(input_directory, output_filename="combined_data.csv"):
    file_pattern = os.path.join(input_directory, "*")
    csv_files = glob.glob(file_pattern)
    
    if not csv_files:
        print(f"No CSV files ending in '_joined.csv' found in {input_directory}")
        return

    dataframes = []

    for file in csv_files:
        filename = os.path.basename(file)
        
        ticker = filename.replace('.csv', '')
        ticker = HANDLE_MAP.get(ticker, ticker)
        
        
        try:
            df = pd.read_csv(file)
            
            df['ticker'] = ticker
            
            dataframes.append(df)
            print(f"Processed: {ticker}")
            
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            
    if dataframes:
        combined_df = pd.concat(dataframes, ignore_index=True)
        
        output_path = os.path.join(input_directory, output_filename)
        combined_df.to_csv(output_path, index=False)
        print(f"\nSuccessfully combined {len(dataframes)} files into '{output_path}'")
    else:
        print("No data was combined.")


combine_ticker_csvs("./x_posts", "all_posts_combined.csv")