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

import pandas as pd
import pandas_market_calendars as mcal

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

ET = ZoneInfo("America/New_York")
TICKERS = ["MSFT", "CRM", "BOX", "QCOM", "HOOD", "SHOP"]
START = datetime(2024, 1, 1, tzinfo=ET)
END = datetime(2026, 7, 17, 23, 59, tzinfo=ET)

nyse = mcal.get_calendar("NYSE")
_schedule = nyse.schedule(start_date=START.date().isoformat(), end_date=END.date().isoformat())
_schedule["market_open"] = _schedule["market_open"].dt.tz_convert(ET)
_schedule["market_close"] = _schedule["market_close"].dt.tz_convert(ET)
_schedule.index = _schedule.index.tz_localize(None)


def tag_session(bars_df: pd.DataFrame) -> pd.DataFrame:
    df = bars_df.copy()
    df["trade_date_naive"] = df["timestamp_et"].dt.normalize().dt.tz_localize(None)
 
    merged = df.merge(
        _schedule[["market_open", "market_close"]],
        left_on="trade_date_naive",
        right_index=True,
        how="left",
    )
 
    def classify(row):
        if pd.isna(row["market_open"]):
            return "closed"
        if row["market_open"] <= row["timestamp_et"] < row["market_close"]:
            return "regular"
        return "extended"
 
    merged["session"] = merged.apply(classify, axis=1)
    return merged.drop(columns=["trade_date_naive", "market_open", "market_close"])

for ticker in TICKERS:
    rq = StockBarsRequest(
        symbol_or_symbols=[ticker],
        timeframe=TimeFrame(1, TimeFrameUnit.Minute),
        start=START,
        end=END,
        adjustment=Adjustment.SPLIT,
        feed=DataFeed.IEX,
    )
    print(f"Fetching {ticker} bars...")
    bars = client.get_stock_bars(rq)[ticker]
    bars = pd.DataFrame([b.model_dump() for b in bars])

    bars["timestamp_et"] = bars["timestamp"].dt.tz_convert(ET)
    et_column = bars.pop("timestamp_et")
    bars.insert(1, "timestamp_et", et_column)

    bars = tag_session(bars)
    session_counts = bars["session"].value_counts().to_dict()
    print(f"  session breakdown: {session_counts}")

    out_path = os.path.join("alpaca_data", f"{ticker}.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_utc", "timestamp_et", "open", "high", "low", "close", "volume", "trade_count", "vwap", "session"])
        for bar in bars.itertuples(index=False):
            writer.writerow([
                bar.timestamp.isoformat(),
                bar.timestamp_et.isoformat(),
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.trade_count,
                bar.vwap,
                bar.session,
            ])
    print(f"Wrote {len(bars)} bars to {out_path}")
    