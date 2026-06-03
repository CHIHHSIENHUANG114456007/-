"""
fetch_stock.py — 股價資料採集（v2：核心精選 6 檔 + 區間漲幅）
專題：整合社群輿情與量化指標之台美股 ETF 趨勢預測系統

v2 變更：
    1. 標的由 3 檔擴充為 6 檔核心精選（0050 / 0056 / 00878 / 00919 / 2330 / TSM）。
    2. 新增「區間漲幅」計算：前一交易日、近一週、近一月、今年以來、近一年，
       輸出彙總檔 performance_summary.csv 供 app 的比較頁直接使用。
    3. CSV 一律存進 data/ 子資料夾，方便 GitHub Actions 自動 commit。

執行方式（本機或 GitHub Actions）：
    pip install yfinance pandas
    python fetch_stock.py

備註：
    開發沙箱網路受限無法連 Yahoo Finance；請在本機 / Colab / GitHub Actions 執行。
    指標與漲幅計算邏輯已用離線資料驗證；連線後即可直接產出真實 CSV。
"""

import os
import sys
import time
import pandas as pd

# 輸出資料夾（GitHub Actions 會把這整個資料夾 commit 回 repo）
DATA_DIR = "data"

# v2 核心精選標的：台股用 .TW 後綴，美股 ADR 直接用代號
TARGETS = {
    "0050.TW": "元大台灣50 ETF",
    "0056.TW": "元大高股息 ETF",
    "00878.TW": "國泰永續高股息 ETF",
    "00919.TW": "群益台灣精選高息 ETF",
    "2330.TW": "台積電",
    "TSM":      "台積電 ADR (美股)",
}

PERIOD = "2y"      # 抓兩年歷史，足夠做技術指標、近一年漲幅與訓練
INTERVAL = "1d"    # 日線


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """加上常見技術指標：5/20 日均線、RSI(14)、日報酬率、漲跌標籤。"""
    df = df.copy()
    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA20"] = df["Close"].rolling(20).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    df["RSI14"] = 100 - (100 / (1 + rs))

    df["Return"] = df["Close"].pct_change()
    df["Target_Up"] = (df["Close"].shift(-1) > df["Close"]).astype(int)
    return df


def pct_change_over(df: pd.DataFrame, trading_days: int) -> float | None:
    """以「往回第 N 個有效收盤」為基準，計算到最新收盤的漲跌幅(%)。

    用交易日數而非日曆天，避免假日造成抓不到基準。
    近一週≈5 個交易日、近一月≈21、近一年≈252。
    """
    closes = df.dropna(subset=["Close"])["Close"].reset_index(drop=True)
    if len(closes) <= trading_days:
        return None
    latest = closes.iloc[-1]
    base = closes.iloc[-1 - trading_days]
    if base == 0:
        return None
    return round((latest - base) / base * 100, 2)


def ytd_change(df: pd.DataFrame) -> float | None:
    """今年以來漲幅(%)：以今年第一個有效收盤為基準。"""
    tmp = df.dropna(subset=["Close"]).copy()
    tmp["Date"] = pd.to_datetime(tmp["Date"], errors="coerce")
    this_year = tmp["Date"].dt.year.max()
    year_rows = tmp[tmp["Date"].dt.year == this_year]
    if year_rows.empty:
        return None
    base = year_rows.iloc[0]["Close"]
    latest = tmp.iloc[-1]["Close"]
    if base == 0:
        return None
    return round((latest - base) / base * 100, 2)


def build_perf_row(name: str, ticker: str, df: pd.DataFrame) -> dict:
    """為單一標的計算各區間漲幅，組成一列彙總資料。"""
    latest = df.dropna(subset=["Close"]).iloc[-1]
    return {
        "ticker": ticker,
        "name": name,
        "close": round(float(latest["Close"]), 2),
        "chg_prev_day": pct_change_over(df, 1),     # 前一交易日 → 今日
        "chg_1w": pct_change_over(df, 5),           # 近一週
        "chg_1m": pct_change_over(df, 21),          # 近一月
        "chg_ytd": ytd_change(df),                  # 今年以來
        "chg_1y": pct_change_over(df, 252),         # 近一年
        "rsi14": round(float(latest["RSI14"]), 1) if pd.notna(latest.get("RSI14")) else None,
    }


def fetch_one(ticker: str) -> pd.DataFrame | None:
    try:
        import yfinance as yf
    except ImportError:
        print("  [錯誤] 尚未安裝 yfinance，請先執行：pip install yfinance")
        sys.exit(1)

    try:
        df = yf.download(ticker, period=PERIOD, interval=INTERVAL,
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df is None or df.empty:
            print(f"  [警告] {ticker} 沒有取得任何資料（代號錯誤或被限流）")
            return None
        df = df.reset_index()  # 讓 Date 變成欄位，方便存檔與 YTD 計算
        df = add_indicators(df)
        return df
    except Exception as e:
        print(f"  [錯誤] 抓取 {ticker} 失敗：{e!r}")
        return None


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print("=" * 60)
    print("股價資料採集 v2 — 6 檔核心精選 + 區間漲幅")
    print("=" * 60)

    perf_rows = []
    ok = 0
    for ticker, name in TARGETS.items():
        print(f"\n>> 正在抓取 {name} ({ticker}) ...")
        df = fetch_one(ticker)
        if df is not None:
            out = os.path.join(DATA_DIR, f"stock_{ticker.replace('.', '_')}.csv")
            df.to_csv(out, index=False, encoding="utf-8-sig")
            perf_rows.append(build_perf_row(name, ticker, df))
            last = df.dropna(subset=["Close"]).iloc[-1]
            print(f"  [成功] 取得 {len(df)} 筆，已存成 {out}")
            print(f"         最新收盤：{last['Close']:.2f}  RSI14：{last['RSI14']:.1f}")
            ok += 1
        time.sleep(1)

    if perf_rows:
        perf = pd.DataFrame(perf_rows)
        perf_out = os.path.join(DATA_DIR, "performance_summary.csv")
        perf.to_csv(perf_out, index=False, encoding="utf-8-sig")
        print(f"\n  [成功] 區間漲幅彙總已存成 {perf_out}")

    # 記錄最後更新時間，app 會讀這個顯示「資料更新於 ...」
    with open(os.path.join(DATA_DIR, "last_updated.txt"), "w", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S"))

    print("\n" + "=" * 60)
    print(f"可行性結論：成功 {ok} / {len(TARGETS)} 檔")
    print("✅ 股價 + 區間漲幅資料就緒" if ok == len(TARGETS)
          else "◐ 部分成功，請檢查失敗標的代號或改用 TWSE 備援")
    print("=" * 60)


if __name__ == "__main__":
    main()
