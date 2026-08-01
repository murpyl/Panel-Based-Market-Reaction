import subprocess
import sys

TARGET_SCRIPT = "join_together.py"


RUN_CONFIGS = [
    ("./x_posts/satyanadella.csv", "alpaca_data/MSFT.csv", "confound_calendar.csv", "./joined_60min/msft_joined_60min.csv", "MSFT"),
    ("./x_posts/Benioff.csv", "alpaca_data/CRM.csv", "confound_calendar.csv", "./joined_60min/crm_joined_60min.csv", "CRM"),
    ("./x_posts/vladtenev.csv", "alpaca_data/HOOD.csv", "confound_calendar.csv", "./joined_60min/hood_joined_60min.csv", "HOOD"),
    ("./x_posts/cristianoamon.csv", "alpaca_data/QCOM.csv", "confound_calendar.csv", "./joined_60min/qcom_joined_60min.csv", "QCOM"),
    ("./x_posts/tobi.csv", "alpaca_data/SHOP.csv", "confound_calendar.csv", "./joined_60min/shop_joined_60min.csv", "SHOP"),
    ("./x_posts/levie.csv", "alpaca_data/BOX.csv", "confound_calendar.csv", "./joined_60min/box_joined_60min.csv", "BOX"),
]

def run_batch():
    total_runs = len(RUN_CONFIGS)
    
    for index, (posts, bars, confound, output, ticker) in enumerate(RUN_CONFIGS, start=1):
        print(f"[{index}/{total_runs}] Starting processing for {ticker}...")
        
        cmd = [
            sys.executable, 
            TARGET_SCRIPT,
            "--posts", posts,
            "--bars", bars,
            "--confound", confound,
            "--output", output,
            "--ticker", ticker
        ]
        
        try:
            subprocess.run(cmd, check=True)
            print(f"[{index}/{total_runs}] Successfully finished {ticker}.\n" + "-"*50)
            
        except subprocess.CalledProcessError as e:
            print(f"[{index}/{total_runs}] ERROR: Script failed for {ticker} with exit code {e.returncode}.", file=sys.stderr)
            print("-" * 50)
            continue

if __name__ == "__main__":
    print(f"Starting batch execution of {len(RUN_CONFIGS)} jobs...\n" + "="*50)
    run_batch()
    print("Batch execution complete.")