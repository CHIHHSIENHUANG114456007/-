"""
analyze_sentiment.py — PTT 輿情情緒分析（本機免費模型）
專題：整合社群輿情與量化指標之台美股 ETF 趨勢預測系統

用途：
    讀取 fetch_ptt.py 產出的 ptt_stock.csv，對每篇文章內文做中文情緒分析，
    再依日期彙總成「每日情緒分數」，輸出兩個檔案：
      - ptt_sentiment.csv      （逐篇情緒分數）
      - daily_sentiment.csv    （每日彙總，供與股價合併）

執行方式（在你自己的電腦上）：
    pip install transformers torch pandas
    python analyze_sentiment.py

重要備註：
    1. 第一次執行會自動下載中文情緒模型權重（約數百 MB，需要網路，只下載一次）。
       下載完成後即可離線使用。
    2. 模型選用 uer/roberta-base-finetuned-jd-binary-chinese：
       針對中文評論微調的二分類（正面/負面）模型，輕量、適合本機跑。
    3. 採半監督精神：模型給文本情緒，再結合推噓數（市場實際反應）做綜合分數，
       對應你們劣勢分析的「用預訓練模型解決標記不足」策略。
"""

import sys
import pandas as pd

MODEL_NAME = "uer/roberta-base-finetuned-jd-binary-chinese"
INPUT_CSV = "ptt_stock.csv"


def load_classifier():
    """載入本機情緒分類器；首次會自動下載模型。"""
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
    """把模型輸出轉成 -1~+1 的情緒分數。正面為正、負面為負，乘信心值。

    先判負面（優先），避免 'negative'/'star 1' 這類標籤被誤判；
    其餘視為正面。涵蓋常見中文情緒模型的標籤命名。
    """
    lab = label.lower()
    is_negative = ("negative" in lab or "label_0" in lab
                   or "star 1" in lab or "star 2" in lab or "1 star" in lab)
    sign = -1 if is_negative else 1
    return round(sign * prob, 4)


def main():
    # 讀取爬蟲結果
    try:
        df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
    except FileNotFoundError:
        print(f"[錯誤] 找不到 {INPUT_CSV}，請先執行 fetch_ptt.py。")
        sys.exit(1)

    if df.empty:
        print("[錯誤] ptt_stock.csv 是空的，沒有文章可分析。")
        sys.exit(1)

    print(f">> 讀入 {len(df)} 篇文章，開始情緒分析...")
    clf = load_classifier()

    # 逐篇分析（用標題+內文摘要）
    text_scores = []
    for i, row in df.iterrows():
        text = f"{row.get('title', '')} {row.get('body', '')}".strip()
        if not text:
            text_scores.append(0.0)
            continue
        try:
            res = clf(text[:512])[0]
            text_scores.append(text_score(res["label"], res["score"]))
        except Exception as e:
            print(f"   [略過] 第 {i} 篇分析失敗：{e!r}")
            text_scores.append(0.0)

    df["text_sentiment"] = text_scores

    # 綜合分數：文本情緒 + 市場實際反應(推噓)。推噓正規化後加權平均。
    # 推文多代表認同、噓文多代表反對，可校正文本判斷。
    max_score = max(df["score"].abs().max(), 1)
    df["push_sentiment"] = (df["score"] / max_score).round(4)
    df["combined_sentiment"] = (0.6 * df["text_sentiment"]
                                + 0.4 * df["push_sentiment"]).round(4)

    df.to_csv("ptt_sentiment.csv", index=False, encoding="utf-8-sig")
    print(f"\n[成功] 逐篇情緒已存成 ptt_sentiment.csv")

    # 依日期彙總成每日情緒分數
    # PTT 日期格式類似 'Mon Feb 10 12:34:56 2025'，轉成日期
    df["parsed_date"] = pd.to_datetime(df["date"], errors="coerce", utc=False)
    df_valid = df.dropna(subset=["parsed_date"]).copy()
    df_valid["day"] = df_valid["parsed_date"].dt.date

    if df_valid.empty:
        print("[警告] 無法解析任何文章日期，跳過每日彙總。")
        print("       可檢查 ptt_stock.csv 的 date 欄格式。")
    else:
        daily = df_valid.groupby("day").agg(
            article_count=("combined_sentiment", "size"),
            avg_sentiment=("combined_sentiment", "mean"),
            avg_text_sentiment=("text_sentiment", "mean"),
            total_push=("push", "sum"),
            total_boo=("boo", "sum"),
        ).round(4).reset_index()
        daily.to_csv("daily_sentiment.csv", index=False, encoding="utf-8-sig")
        print(f"[成功] 每日情緒已存成 daily_sentiment.csv（{len(daily)} 天）")

    print("\n" + "=" * 60)
    print("情緒分析完成。下一步：")
    print("  把 daily_sentiment.csv 依日期 join 到 stock_*.csv，")
    print("  形成『技術指標 + 當日情緒』的訓練特徵表，即可訓練漲跌模型。")
    print("=" * 60)


if __name__ == "__main__":
    main()
