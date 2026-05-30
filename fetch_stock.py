"""
fetch_stock.py — 股價資料採集與可行性驗證腳本
專題：整合社群輿情與量化指標之台美股 ETF 趨勢預測系統

用途：
    驗證能否穩定取得 0050、台積電(2330)、台積電 ADR(TSM) 的歷史股價，
    並計算基本技術指標(MA, RSI)，輸出為 CSV 供後續模型使用。

執行方式（在你自己的電腦上）：
    pip install yfinance pandas
    python fetch_stock.py

備註：
    本腳本在受限網路的沙箱中無法連外，請在本機或 Google Colab 執行。
    yfinance 連 Yahoo Finance；若 Yahoo 不穩，TWSE 區塊提供台股官方來源備援。
"""

import sys
import time
import pandas as pd

# 要採集的標的：台股用 .TW 後綴，美股 ADR 直接用代號
TARGETS = {
    "0050.TW": "元大台灣50 ETF",
    "2330.TW": "台積電",
    "TSM":     "台積電 ADR (美股)",
}

PERIOD = "2y"      # 抓兩年歷史，足夠做技術指標與訓練
INTERVAL = "1d"    # 日線


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """加上常見技術指標：5/20 日均線、RSI(14)、日報酬率、漲跌標籤。"""
    df = df.copy()
    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA20"] = df["Close"].rolling(20).mean()

    # RSI(14)
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    df["RSI14"] = 100 - (100 / (1 + rs))

    # 日報酬率與「隔日是否上漲」標籤（這就是模型要預測的 y）
    df["Return"] = df["Close"].pct_change()
    df["Target_Up"] = (df["Close"].shift(-1) > df["Close"]).astype(int)
    return df


def fetch_one(ticker: str) -> pd.DataFrame | None:
    """用 yfinance 抓單一標的，回傳含指標的 DataFrame；失敗回傳 None。"""
    try:
        import yfinance as yf
    except ImportError:
        print("  [錯誤] 尚未安裝 yfinance，請先執行：pip install yfinance")
        sys.exit(1)

    try:
        df = yf.download(ticker, period=PERIOD, interval=INTERVAL,
                         progress=False, auto_adjust=True)
        # yfinance 新版回傳 MultiIndex 欄位，攤平它
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df is None or df.empty:
            print(f"  [警告] {ticker} 沒有取得任何資料（可能代號錯誤或被限流）")
            return None
        df = add_indicators(df)
        return df
    except Exception as e:
        print(f"  [錯誤] 抓取 {ticker} 失敗：{e!r}")
        return None


def main():
    print("=" * 60)
    print("股價資料採集 — 可行性驗證")
    print("=" * 60)

    results = {}
    for ticker, name in TARGETS.items():
        print(f"\n>> 正在抓取 {name} ({ticker}) ...")
        df = fetch_one(ticker)
        if df is not None:
            out = f"stock_{ticker.replace('.', '_')}.csv"
            df.to_csv(out, encoding="utf-8-sig")
            last = df.dropna(subset=["Close"]).iloc[-1]
            print(f"  [成功] 取得 {len(df)} 筆，已存成 {out}")
            print(f"         最新收盤：{last['Close']:.2f}  "
                  f"MA20：{last['MA20']:.2f}  RSI14：{last['RSI14']:.1f}")
            results[ticker] = df
        time.sleep(1)  # 禮貌性間隔，避免被限流

    print("\n" + "=" * 60)
    print(f"可行性結論：成功 {len(results)} / {len(TARGETS)} 檔")
    if len(results) == len(TARGETS):
        print("✅ 股價資料來源可行，可進入下一步（輿情採集 + 特徵合併）")
    elif results:
        print("◐ 部分成功。建議檢查失敗標的代號，或改用 TWSE 官方 API 備援。")
    else:
        print("❌ 全數失敗。請確認網路、yfinance 版本，或改用官方資料源。")
    print("=" * 60)


if __name__ == "__main__":
    main()
