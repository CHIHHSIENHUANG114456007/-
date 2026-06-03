"""
analyze_sentiment.py — PTT 輿情情緒分析（v2：本機免費模型 + 分標的彙總）
專題：整合社群輿情與量化指標之台美股 ETF 趨勢預測系統

v2 變更：
    1. 讀寫一律走 data/ 子資料夾，配合 GitHub Actions。
    2. 除了「每日整體情緒」，另輸出「每日 × 標的」情緒，
       讓 app 能依使用者選的標的顯示對應輿情。

輸出：
    - data/ptt_sentiment.csv         （逐篇情緒分數）
    - data/daily_sentiment.csv       （每日整體彙總，沿用 v1 欄位，向下相容）
    - data/daily_sentiment_by_target.csv （每日 × 標的彙總，v2 新增）

執行方式（本機或 GitHub Actions）：
    pip install transformers torch pandas
    python analyze_sentiment.py

備註：
    首次執行會下載中文情緒模型權重（約數百 MB，只下載一次）。
    模型：uer/roberta-base-finetuned-jd-binary-chinese（中文評論二分類，輕量）。
"""

import os
import sys
import pandas as pd

DATA_DIR = "data"
MODEL_NAME = "uer/roberta-base-finetuned-jd-binary-chinese"
INPUT_CSV = os.path.join(DATA_DIR, "ptt_stock.csv")


def load_classifier():
    try:
        from transformers import pipeline
    except ImportError:
        print("[錯誤] 尚未安裝 transformers，請先執行：pip install transformers torch")
        sys.exit(1)
    print(">> 載入中文情緒模型（首次執行會下載權重，請稍候）...")
    clf = pipeline("sentiment-analysis", model=MODEL_NAME,
                   tokenizer=MODEL_NAME, truncation=True, max_length=512)
    print("   模型載入完成。")
    return clf


def text_score(label: str, prob: float) -> float:
    lab = label.lower()
    is_negative = ("negative" in lab or "label_0" in lab
                   or "star 1" in lab or "star 2" in lab or "1 star" in lab)
    sign = -1 if is_negative else 1
    return round(sign * prob, 4)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
    except FileNotFoundError:
        # 找不到 PTT 資料時，正常結束（exit 0）而非報錯中斷整個流程。
        # 常見原因：PTT 在海外伺服器(GitHub Actions)連線被限制，fetch_ptt 沒抓到文章。
        # 股價資料不受影響，情緒分析待 PTT 可連線時再補。
        print(f"[略過] 找不到 {INPUT_CSV}（PTT 可能未成功抓取），跳過情緒分析。")
        return
    if df.empty:
        print("[略過] ptt_stock.csv 是空的，沒有文章可分析，跳過情緒分析。")
        return

    print(f">> 讀入 {len(df)} 篇文章，開始情緒分析...")
    clf = load_classifier()

    scores = []
    for i, row in df.iterrows():
        text = f"{row.get('title', '')} {row.get('body', '')}".strip()
        if not text:
            scores.append(0.0)
            continue
        try:
            res = clf(text[:512])[0]
            scores.append(text_score(res["label"], res["score"]))
        except Exception as e:
            print(f"   [略過] 第 {i} 篇分析失敗：{e!r}")
            scores.append(0.0)
    df["text_sentiment"] = scores

    max_score = max(df["score"].abs().max(), 1)
    df["push_sentiment"] = (df["score"] / max_score).round(4)
    df["combined_sentiment"] = (0.6 * df["text_sentiment"]
                                + 0.4 * df["push_sentiment"]).round(4)

    df.to_csv(os.path.join(DATA_DIR, "ptt_sentiment.csv"),
              index=False, encoding="utf-8-sig")
    print("[成功] 逐篇情緒已存成 data/ptt_sentiment.csv")

    # ---- 日期解析 ----
    df["parsed_date"] = pd.to_datetime(df["date"], errors="coerce", utc=False)
    df_valid = df.dropna(subset=["parsed_date"]).copy()
    df_valid["day"] = df_valid["parsed_date"].dt.date

    if df_valid.empty:
        print("[警告] 無法解析任何文章日期，跳過每日彙總。")
        return

    # ---- (A) 每日整體（沿用 v1 欄位，向下相容）----
    daily = df_valid.groupby("day").agg(
        article_count=("combined_sentiment", "size"),
        avg_sentiment=("combined_sentiment", "mean"),
        avg_text_sentiment=("text_sentiment", "mean"),
        total_push=("push", "sum"),
        total_boo=("boo", "sum"),
    ).round(4).reset_index()
    daily.to_csv(os.path.join(DATA_DIR, "daily_sentiment.csv"),
                 index=False, encoding="utf-8-sig")
    print(f"[成功] 每日整體情緒已存成 data/daily_sentiment.csv（{len(daily)} 天）")

    # ---- (B) 每日 × 標的（v2 新增）----
    # 一篇文章可能命中多個標的，展開成多列再分組
    if "targets" in df_valid.columns:
        exploded = df_valid.assign(
            target=df_valid["targets"].fillna("").str.split(",")
        ).explode("target")
        exploded = exploded[exploded["target"].str.strip() != ""]
        if not exploded.empty:
            by_target = exploded.groupby(["day", "target"]).agg(
                article_count=("combined_sentiment", "size"),
                avg_sentiment=("combined_sentiment", "mean"),
                total_push=("push", "sum"),
                total_boo=("boo", "sum"),
            ).round(4).reset_index()
            by_target.to_csv(
                os.path.join(DATA_DIR, "daily_sentiment_by_target.csv"),
                index=False, encoding="utf-8-sig")
            print(f"[成功] 每日×標的情緒已存成 "
                  f"data/daily_sentiment_by_target.csv（{len(by_target)} 列）")

    print("\n情緒分析完成。下一步：streamlit run app.py")


if __name__ == "__main__":
    main()
