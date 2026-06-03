# 台美股輿情 × 量化趨勢分析系統 — v2

第二版在 v1 基礎上做了四大升級：**標的擴充、區間漲幅比較、每日自動更新、兩款新介面主題**。
台美股輿情 × 量化趨勢分析仍是整個系統的主軸。

---

## 一、v1 → v2 改了什麼

| 項目 | v1 | v2 |
| --- | --- | --- |
| 標的數量 | 3 檔（0050、2330、TSM） | 6 檔核心精選（+ 0056、00878、00919） |
| 漲幅比較 | 無 | 前一交易日 / 近一週 / 近一月 / 今年以來 / 近一年 |
| 頁面 | 單頁 | 單一標的分析 / 多標的比較 / 市場總覽 |
| 資料更新 | 手動跑腳本 | GitHub Actions 每日自動更新並 commit |
| 介面主題 | System / Light / Dark | 再加「新手友善版」「四季風景版」 |
| 情緒粒度 | 全市場每日 | 全市場每日 +（每日 × 標的） |

設計上參考了 twetf.com 的「市場總覽 / 多標的橫向比較」概念，但資料來源維持你自己爬的
yfinance + PTT，因此聚焦在 6 檔核心精選，避免爬蟲與情緒分析負擔過重。

---

## 二、資料夾結構

```
v2/
├── app.py                       # 主應用程式（Streamlit）
├── fetch_stock.py               # 股價採集 + 區間漲幅彙總
├── fetch_ptt.py                 # PTT 輿情採集（6 檔關鍵字）
├── analyze_sentiment.py         # 中文情緒分析 + 每日/分標的彙總
├── requirements.txt             # app 執行所需套件
├── requirements-crawler.txt     # 採集腳本所需套件（含 torch/transformers）
├── .streamlit/config.toml       # Streamlit 預設主題
├── .github/workflows/
│   └── daily_update.yml         # 每日自動更新排程
└── data/                        # 所有 CSV 都放這（由腳本產生、Actions 自動更新）
    ├── stock_0050_TW.csv ...    # 各標的歷史股價 + 指標
    ├── performance_summary.csv  # 各標的區間漲幅彙總
    ├── daily_sentiment.csv      # 全市場每日情緒
    ├── daily_sentiment_by_target.csv  # 每日 × 標的情緒
    ├── ptt_stock.csv / ptt_sentiment.csv
    └── last_updated.txt         # 最後更新時間（app 會顯示）
```

> 注意：`app.py` 會優先讀 `data/` 內的檔；若沒有，會退回同層找（向下相容 v1）。

---

## 三、為什麼要在你自己的電腦 / GitHub 上跑

採集腳本需連 Yahoo Finance 與 PTT。**開發沙箱網路被限制在白名單內連不出去**
（會看到 `Host not in allowlist`）——這是環境限制，不是程式錯誤。
計算邏輯（指標、區間漲幅、推噓解析、情緒彙總）皆已用你的真實 CSV 離線驗證通過。

---

## 四、本機快速開始

```bash
# 1. 安裝 app 套件
pip install -r requirements.txt

# 2.（首次）安裝採集套件並產生資料
pip install -r requirements-crawler.txt
python fetch_stock.py        # → data/stock_*.csv + performance_summary.csv
python fetch_ptt.py          # → data/ptt_stock.csv
python analyze_sentiment.py  # → data/daily_sentiment*.csv

# 3. 啟動 app
streamlit run app.py         # 瀏覽器開 http://localhost:8501
```

---

## 五、每日自動更新（GitHub Actions）

`.github/workflows/daily_update.yml` 已設定好：

1. 每個交易日（週一～五）台灣時間 17:30 自動觸發，也可在 Actions 頁手動 `Run workflow`。
2. 依序跑 `fetch_stock.py → fetch_ptt.py → analyze_sentiment.py`，把 `data/` commit 回 repo。
3. Streamlit Cloud 偵測到新 commit 會**自動重新部署**，前台即顯示最新資料。

**設定步驟：**
1. 把整個 `v2/` 推上 GitHub repo。
2. repo → Settings → Actions → General → Workflow permissions
   勾選 **Read and write permissions**（讓 Actions 能 commit）。
3. 到 Streamlit Cloud 用這個 repo 部署，主程式指向 `app.py`。
4. 想立刻測試：Actions 分頁 → 「每日資料更新」→ Run workflow。

> 為何用 Actions 而非 Streamlit 背景排程？Streamlit Cloud 免費版不提供常駐背景工作，
> 用 GitHub Actions（免費額度充足）跑爬蟲再 commit 是最穩、零成本的做法。

---

## 六、五種介面主題

- **Dark / Light / System**：沿用 v1，System 會跟隨作業系統深淺色。
- **新手友善版**：乾淨大字、柔和配色；內建「股市用詞小教室」（收盤、MA、RSI、ETF…）
  與「趨勢傾向判斷說明」，把每個訊號怎麼加總講清楚，適合不懂股市的觀眾。
- **四季風景版**：請求瀏覽器**地理定位**取得經緯度 → 用緯度判斷半球(南北半球季節相反)、
  用經度換算當地時間、並反查城市名顯示。因此不同城市/時區的使用者會看到不同背景
  (例如台北是冬天時，雪梨會是夏天)。使用者拒絕定位授權時，退回瀏覽器本地時鐘。
  背景為耐看的低飽和動態漸層，文字加陰影確保任何季節都清楚可讀。

---

## 七、誠實的限制與後續

- 「趨勢傾向」是 **RSI + 均線 + 輿情** 的規則版示意，**不是 ML 預測、不構成投資建議**。
  正式機器學習漲跌模型需累積數月輿情後訓練（LightGBM/LSTM + SHAP 可解釋性），為後續開發。
- 四季風景版已以**地理定位(經緯度)**客製化：緯度→半球季節、經度→當地時間、反查城市名。
  使用者需在瀏覽器允許定位授權；拒絕時自動退回本地時鐘。
  (註：經度換算時間為粗估，未套用各國夏令時間；如需精準時區可再接時區 API。)

本系統為學術專題用途，所有內容僅供研究參考，不構成任何投資建議。
