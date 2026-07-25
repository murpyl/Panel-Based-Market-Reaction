import os
import csv
import datetime
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import Adjustment, DataFeed

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

ET = ZoneInfo("America/New_York")
TICKERS = ["MSFT", "CRM", "BOX", "QCOM", "HOOD", "SHOP"]
START = datetime(2024, 1, 1, tzinfo=ET)
END = datetime(2026, 7, 17, 23, 59, tzinfo=ET)

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)


for ticker in TICKERS:
    rq = StockBarsRequest(
        symbol_or_symbols=[ticker],
        timeframe=TimeFrame(1, TimeFrameUnit.Minute),
        start=START,
        end=END,
        adjustment=Adjustment.SPLIT,
        data_feed=DataFeed.IEX,
    )
    print(f"Fetching {ticker} bars...")
    bars = client.get_stock_bars(rq)[ticker]
    out_path = os.path.join("alpaca_data", f"{ticker}.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_utc", "open", "high", "low", "close", "volume", "trade_count", "vwap"])
        for bar in bars:
            writer.writerow([
                bar.timestamp.isoformat(),
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.trade_count,
                bar.vwap,
            ])
    print(f"Wrote {len(bars)} bars to {out_path}")
    