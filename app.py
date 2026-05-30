"""
app.py — 台美股輿情 × 量化趨勢分析儀表板
專題：整合社群輿情與量化指標之台美股 ETF 趨勢預測系統

這是專題的主應用程式（MVP）。整合三項已驗證的資料：
  - 歷史股價與技術指標（stock_*.csv）
  - 每日輿情情緒（daily_sentiment.csv）
  - 逐篇 PTT 情緒（ptt_sentiment.csv）

功能：
  1. 多標的切換（0050 / 台積電 2330 / 台積電 ADR）
  2. 互動股價走勢圖 + 均線 + 成交量
  3. RSI 技術指標圖（超買/超賣區）
  4. PTT 輿情情緒視覺化
  5. 規則版趨勢傾向判斷（誠實標示為示意，模型待資料累積後升級）

執行方式（在你自己的電腦上）：
    pip install streamlit plotly pandas
    streamlit run app.py
  執行後瀏覽器會自動打開，網址通常是 http://localhost:8501

備註：請把本檔放在與那些 CSV 同一個資料夾（跑程式\\files）再執行。
"""

import os
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------- 基本設定 ----------
st.set_page_config(page_title="台美股輿情 × 量化趨勢分析",
                   page_icon="📊", layout="wide")

TARGETS = {
    "元大台灣50 (0050)": "stock_0050_TW.csv",
    "台積電 (2330)": "stock_2330_TW.csv",
    "台積電 ADR (TSM)": "stock_TSM.csv",
}

# ---------- 樣式：深色金融儀表板風格 ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Lexend:wght@300;500;700&family=JetBrains+Mono:wght@500&display=swap');
.stApp { background: #0d1117; }
html, body, [class*="css"] { font-family: 'Lexend', sans-serif; color: #e6edf3; }
.main-title { font-size: 2.1rem; font-weight: 700; color: #f0f6fc;
  letter-spacing: -0.5px; margin-bottom: 0; }
.subtitle { color: #7d8590; font-size: 0.95rem; margin-top: 0.2rem; }
.metric-card { background: linear-gradient(145deg, #161b22, #1c2129);
  border: 1px solid #30363d; border-radius: 14px; padding: 1.1rem 1.3rem;
  box-shadow: 0 4px 16px rgba(0,0,0,0.3); }
.metric-label { color: #7d8590; font-size: 0.8rem; text-transform: uppercase;
  letter-spacing: 1px; }
.metric-value { font-family: 'JetBrains Mono', monospace; font-size: 1.7rem;
  font-weight: 500; color: #f0f6fc; margin-top: 0.2rem; }
.tag { display:inline-block; padding: 0.15rem 0.6rem; border-radius: 6px;
  font-size: 0.75rem; font-weight: 500; }
.disclaimer { background: rgba(187, 128, 9, 0.12); border-left: 3px solid #bb8009;
  padding: 0.7rem 1rem; border-radius: 6px; color: #d9b25b; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)


# ---------- 資料載入 ----------
@st.cache_data
def load_stock(filename):
    if not os.path.exists(filename):
        return None
    df = pd.read_csv(filename, encoding="utf-8-sig")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df.dropna(subset=["Date"])


@st.cache_data
def load_csv(filename):
    if not os.path.exists(filename):
        return None
    return pd.read_csv(filename, encoding="utf-8-sig")


# ---------- 標題 ----------
st.markdown('<p class="main-title">📊 台美股輿情 × 量化趨勢分析</p>',
            unsafe_allow_html=True)
st.markdown('<p class="subtitle">整合社群輿情情緒與技術指標的 ETF 趨勢分析系統 · 專題 MVP</p>',
            unsafe_allow_html=True)
st.write("")

# ---------- 側邊欄 ----------
with st.sidebar:
    st.header("⚙️ 控制面板")
    target_name = st.selectbox("選擇標的", list(TARGETS.keys()))
    st.divider()
    show_ma = st.checkbox("顯示移動平均線 (MA5/MA20)", value=True)
    show_volume = st.checkbox("顯示成交量", value=True)
    days = st.slider("顯示天數", 30, 500, 120)
    st.divider()
    st.caption("資料來源：yfinance（股價）+ PTT Stock 板（輿情）")

stock = load_stock(TARGETS[target_name])

if stock is None:
    st.error(f"找不到 {TARGETS[target_name]}，請確認本檔與 CSV 放在同一個資料夾。")
    st.stop()

stock = stock.tail(days).reset_index(drop=True)
latest = stock.dropna(subset=["Close"]).iloc[-1]
prev = stock.dropna(subset=["Close"]).iloc[-2] if len(stock) > 1 else latest
change = latest["Close"] - prev["Close"]
change_pct = (change / prev["Close"] * 100) if prev["Close"] else 0

# ---------- 關鍵指標卡 ----------
daily_sent = load_csv("daily_sentiment.csv")
avg_sent = daily_sent["avg_sentiment"].mean() if daily_sent is not None else None

c1, c2, c3, c4 = st.columns(4)
color = "#3fb950" if change >= 0 else "#f85149"
arrow = "▲" if change >= 0 else "▼"
with c1:
    st.markdown(f'<div class="metric-card"><div class="metric-label">最新收盤</div>'
                f'<div class="metric-value">{latest["Close"]:.2f}</div></div>',
                unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="metric-card"><div class="metric-label">漲跌</div>'
                f'<div class="metric-value" style="color:{color}">{arrow} {abs(change):.2f} '
                f'({change_pct:+.2f}%)</div></div>', unsafe_allow_html=True)
with c3:
    rsi = latest.get("RSI14", float("nan"))
    rsi_txt = f"{rsi:.1f}" if pd.notna(rsi) else "—"
    rsi_state = "超買" if pd.notna(rsi) and rsi > 70 else ("超賣" if pd.notna(rsi) and rsi < 30 else "中性")
    st.markdown(f'<div class="metric-card"><div class="metric-label">RSI(14) · {rsi_state}</div>'
                f'<div class="metric-value">{rsi_txt}</div></div>', unsafe_allow_html=True)
with c4:
    sent_txt = f"{avg_sent:+.2f}" if avg_sent is not None else "—"
    sent_color = "#3fb950" if (avg_sent or 0) >= 0 else "#f85149"
    st.markdown(f'<div class="metric-card"><div class="metric-label">PTT 輿情情緒</div>'
                f'<div class="metric-value" style="color:{sent_color}">{sent_txt}</div></div>',
                unsafe_allow_html=True)

st.write("")

# ---------- 股價圖 ----------
st.subheader(f"📈 {target_name} 走勢")
rows = 2 if show_volume else 1
fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                    row_heights=[0.72, 0.28] if show_volume else [1],
                    vertical_spacing=0.04)

fig.add_trace(go.Candlestick(
    x=stock["Date"], open=stock["Open"], high=stock["High"],
    low=stock["Low"], close=stock["Close"], name="價格",
    increasing_line_color="#3fb950", decreasing_line_color="#f85149"), row=1, col=1)

if show_ma:
    if "MA5" in stock:
        fig.add_trace(go.Scatter(x=stock["Date"], y=stock["MA5"], name="MA5",
                                 line=dict(color="#58a6ff", width=1.3)), row=1, col=1)
    if "MA20" in stock:
        fig.add_trace(go.Scatter(x=stock["Date"], y=stock["MA20"], name="MA20",
                                 line=dict(color="#d29922", width=1.3)), row=1, col=1)

if show_volume and "Volume" in stock:
    fig.add_trace(go.Bar(x=stock["Date"], y=stock["Volume"], name="成交量",
                         marker_color="#30506b"), row=2, col=1)

fig.update_layout(template="plotly_dark", height=520, paper_bgcolor="rgba(0,0,0,0)",
                  plot_bgcolor="rgba(0,0,0,0)", xaxis_rangeslider_visible=False,
                  legend=dict(orientation="h", y=1.08), margin=dict(t=30, b=10))
st.plotly_chart(fig, width='stretch')

# ---------- RSI 圖 ----------
if "RSI14" in stock:
    st.subheader("📉 RSI(14) 相對強弱指標")
    rfig = go.Figure()
    rfig.add_trace(go.Scatter(x=stock["Date"], y=stock["RSI14"], name="RSI",
                              line=dict(color="#bc8cff", width=1.6)))
    rfig.add_hline(y=70, line_dash="dash", line_color="#f85149",
                   annotation_text="超買 70")
    rfig.add_hline(y=30, line_dash="dash", line_color="#3fb950",
                   annotation_text="超賣 30")
    rfig.update_layout(template="plotly_dark", height=260,
                       paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                       margin=dict(t=20, b=10), yaxis_range=[0, 100])
    st.plotly_chart(rfig, width='stretch')

# ---------- 輿情區 ----------
st.subheader("💬 PTT 輿情情緒分析")
col_a, col_b = st.columns([1, 1])

with col_a:
    if daily_sent is not None and not daily_sent.empty:
        sfig = go.Figure()
        colors = ["#3fb950" if v >= 0 else "#f85149"
                  for v in daily_sent["avg_sentiment"]]
        sfig.add_trace(go.Bar(x=daily_sent["day"], y=daily_sent["avg_sentiment"],
                              marker_color=colors, name="每日情緒"))
        sfig.update_layout(template="plotly_dark", height=300, title="每日綜合情緒分數",
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           margin=dict(t=40, b=10))
        st.plotly_chart(sfig, width='stretch')
    else:
        st.info("尚無每日情緒資料，請先執行 analyze_sentiment.py")

with col_b:
    ptt = load_csv("ptt_sentiment.csv")
    if ptt is not None and "combined_sentiment" in ptt:
        hfig = go.Figure()
        hfig.add_trace(go.Histogram(x=ptt["combined_sentiment"], nbinsx=20,
                                    marker_color="#58a6ff"))
        hfig.update_layout(template="plotly_dark", height=300, title="逐篇情緒分數分布",
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           margin=dict(t=40, b=10))
        st.plotly_chart(hfig, width='stretch')
    else:
        st.info("尚無逐篇情緒資料")

# ---------- 規則版趨勢傾向 ----------
st.subheader("🧭 趨勢傾向判斷")
st.markdown('<div class="disclaimer">⚠️ 以下為<b>規則版示意判斷</b>，'
            '結合 RSI 與當前輿情情緒方向綜合給出傾向。'
            '正式機器學習預測模型需累積數月輿情資料後訓練，為本專題後續開發項目。</div>',
            unsafe_allow_html=True)
st.write("")

signals = []
score = 0
if pd.notna(rsi):
    if rsi < 30:
        signals.append("RSI 進入超賣區（< 30），技術面偏向反彈"); score += 1
    elif rsi > 70:
        signals.append("RSI 進入超買區（> 70），技術面偏向回檔"); score -= 1
    else:
        signals.append(f"RSI 中性（{rsi:.1f}），技術面無明確訊號")
if "MA5" in stock and "MA20" in stock and pd.notna(latest.get("MA20")):
    if latest["MA5"] > latest["MA20"]:
        signals.append("MA5 在 MA20 之上，短期趨勢偏多"); score += 1
    else:
        signals.append("MA5 在 MA20 之下，短期趨勢偏空"); score -= 1
if avg_sent is not None:
    if avg_sent > 0.1:
        signals.append(f"PTT 輿情偏正面（{avg_sent:+.2f}），市場情緒樂觀"); score += 1
    elif avg_sent < -0.1:
        signals.append(f"PTT 輿情偏負面（{avg_sent:+.2f}），市場情緒悲觀"); score -= 1
    else:
        signals.append("PTT 輿情中性")

verdict = ("偏多 📈", "#3fb950") if score > 0 else \
          (("偏空 📉", "#f85149") if score < 0 else ("中性 ⚖️", "#d29922"))
st.markdown(f"### 綜合傾向：<span style='color:{verdict[1]}'>{verdict[0]}</span>",
            unsafe_allow_html=True)
for s in signals:
    st.markdown(f"- {s}")

st.write("")
st.caption("本系統為學術專題用途，所有內容僅供研究參考，不構成任何投資建議。")
