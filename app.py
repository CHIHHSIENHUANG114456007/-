"""
app.py — 台美股輿情 × 量化趨勢分析儀表板 (v2)
專題：整合社群輿情與量化指標之台美股 ETF 趨勢預測系統

v2 重點：
  1. 標的擴充為 6 檔核心精選（0050 / 0056 / 00878 / 00919 / 2330 / TSM），
     並參考 twetf.com 加入「市場總覽」與「多標的比較」頁。
  2. 區間漲幅比較：前一交易日 / 近一週 / 近一月 / 今年以來 / 近一年。
  3. 資料每日由 GitHub Actions 自動更新（讀 data/ 內 CSV 與 last_updated.txt）。
  4. 五種介面主題：
        System / Light / Dark（沿用 v1）
        新手友善版（乾淨簡單 + 股市用詞教學 + 趨勢判斷說明）
        四季風景版（依使用者所在城市的當地時間 → 季節 + 日夜，動態漸層背景）

執行方式（本機）：
    pip install streamlit plotly pandas
    streamlit run app.py
    瀏覽器會自動打開 http://localhost:8501

備註：請確保 data/ 資料夾與本檔同層，內含 stock_*.csv、performance_summary.csv、
      daily_sentiment.csv 等（由三支採集腳本產生）。
"""

import os
import datetime as dt
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ============================================================
# 基本設定與常數
# ============================================================
st.set_page_config(page_title="台美股輿情 × 量化趨勢分析",
                   page_icon="📊", layout="wide")

DATA_DIR = "data"

TARGETS = {
    "元大台灣50 (0050)":      ("stock_0050_TW.csv", "0050"),
    "元大高股息 (0056)":      ("stock_0056_TW.csv", "0056"),
    "國泰永續高股息 (00878)": ("stock_00878_TW.csv", "00878"),
    "群益台灣精選高息 (00919)": ("stock_00919_TW.csv", "00919"),
    "台積電 (2330)":          ("stock_2330_TW.csv", "2330"),
    "台積電 ADR (TSM)":       ("stock_TSM.csv", "TSM"),
}

# 股市用詞教學（新手友善版用）
GLOSSARY = [
    ("收盤價", "當天交易結束時的最後成交價格，是最常被引用的股價。"),
    ("漲跌幅 %", "今天股價相對前一天的變化百分比。正數代表上漲，負數代表下跌。"),
    ("MA 移動平均線", "最近 N 天收盤價的平均。MA5 是近 5 天平均、MA20 是近 20 天平均，用來看趨勢方向。"),
    ("黃金交叉 / 死亡交叉", "短期均線(MA5)向上穿過長期均線(MA20)叫黃金交叉，常被視為偏多訊號；反之向下穿過叫死亡交叉，偏空。"),
    ("RSI 相對強弱指標", "0~100 的數值。一般 >70 代表「超買」(可能過熱回檔)、<30 代表「超賣」(可能跌深反彈)。"),
    ("成交量", "當天買賣成交的股數(台股以「張」為單位，1 張 = 1000 股)。量大代表交投熱絡。"),
    ("ETF", "指數股票型基金，像一籃子股票打包成一檔，買一張就等於分散投資多家公司，例如 0050 涵蓋台灣前 50 大公司。"),
    ("輿情情緒分數", "本系統用 AI 模型分析 PTT 股板文章，得到 -1(極負面) 到 +1(極正面) 的分數，反映散戶討論氛圍。"),
]

# 趨勢傾向判斷說明（新手友善版用）
VERDICT_EXPLAIN = (
    "本系統的「趨勢傾向」是把三個訊號加總後的綜合方向，**不是預測、也不是買賣建議**：\n\n"
    "1. **RSI**：超賣(<30)記 +1、超買(>70)記 −1。\n"
    "2. **均線**：MA5 在 MA20 之上記 +1、之下記 −1。\n"
    "3. **輿情情緒**：偏正面記 +1、偏負面記 −1。\n\n"
    "三項加總 > 0 顯示「偏多」、< 0 顯示「偏空」、=0 顯示「中性」。"
    "這是規則版示意，正式機器學習模型會在累積數月輿情後訓練。"
)


# ============================================================
# 主題系統（含新手友善版、四季風景版）
# ============================================================
def detect_season_and_phase():
    """依使用者『所在地理位置 + 當地時間』推估季節與日夜階段。

    座標由 streamlit-geolocation 元件取得後存在 st.session_state['_geo']；
    取不到時退回伺服器/瀏覽器時鐘的月份與當下時段。
    回傳 (季節, 日夜, 城市名, 緯度)。
    """
    now = dt.datetime.now()
    geo = st.session_state.get("_geo")  # {'lat':.., 'lon':.., 'city':..} 或 None

    lat = None
    city = ""
    if geo and geo.get("lat") is not None:
        lat = float(geo["lat"])
        city = geo.get("city", "") or ""
        lon = float(geo["lon"]) if geo.get("lon") is not None else 0.0
        # 以經度估當地時間（每 15 度約 1 小時）
        utc_h = dt.datetime.now(dt.timezone.utc).hour
        hour = int((utc_h + lon / 15) % 24)
        month = now.month
    else:
        hour, month = now.hour, now.month

    northern = lat is None or lat >= 0
    if month in (3, 4, 5):
        season = "spring" if northern else "autumn"
    elif month in (6, 7, 8):
        season = "summer" if northern else "winter"
    elif month in (9, 10, 11):
        season = "autumn" if northern else "spring"
    else:
        season = "winter" if northern else "summer"

    if 5 <= hour < 11:
        phase = "morning"
    elif 11 <= hour < 17:
        phase = "day"
    elif 17 <= hour < 20:
        phase = "dusk"
    else:
        phase = "night"
    return season, phase, city, lat


# 四季 × 日夜 漸層配色（耐看、低飽和，避免干擾讀圖）
SEASON_GRADIENTS = {
    ("spring", "morning"): ("#ffeef2", "#e8f5e9", "#2c3e2e"),
    ("spring", "day"):     ("#fce4ec", "#e0f2f1", "#2c3e2e"),
    ("spring", "dusk"):    ("#f8bbd0", "#c5cae9", "#2a2438"),
    ("spring", "night"):   ("#2a2438", "#1a2235", "#e8eaf6"),
    ("summer", "morning"): ("#e1f5fe", "#fff9c4", "#1b3a2e"),
    ("summer", "day"):     ("#b3e5fc", "#e0f7fa", "#0d2818"),
    ("summer", "dusk"):    ("#ffccbc", "#80deea", "#2a1f1a"),
    ("summer", "night"):   ("#0d2818", "#102027", "#e0f7fa"),
    ("autumn", "morning"): ("#fff3e0", "#ffe0b2", "#3a2a1a"),
    ("autumn", "day"):     ("#ffe0b2", "#ffccbc", "#3a2a1a"),
    ("autumn", "dusk"):    ("#ff8a65", "#5d4037", "#fff3e0"),
    ("autumn", "night"):   ("#2a1a10", "#1a1410", "#ffe0b2"),
    ("winter", "morning"): ("#eceff1", "#e3f2fd", "#1a2733"),
    ("winter", "day"):     ("#e3f2fd", "#eceff1", "#1a2733"),
    ("winter", "dusk"):    ("#b0bec5", "#78909c", "#eceff1"),
    ("winter", "night"):   ("#101820", "#0d1117", "#e3f2fd"),
}

SEASON_LABEL = {"spring": "🌸 春", "summer": "🌊 夏", "autumn": "🍁 秋", "winter": "❄️ 冬"}
PHASE_LABEL = {"morning": "清晨", "day": "白天", "dusk": "黃昏", "night": "夜晚"}


def request_geolocation():
    """用 streamlit-geolocation 元件請求瀏覽器定位（會在元件 iframe 內執行，
    腳本能正常跑、且帶 allow=geolocation，因此手機/電腦都會跳出授權詢問）。
    取得座標後反查城市名，存進 st.session_state['_geo']。
    若套件未安裝或使用者未授權，靜默退回時鐘判斷。"""
    try:
        from streamlit_geolocation import streamlit_geolocation
    except Exception:
        st.info("（四季風景版的定位功能需要 streamlit-geolocation 套件；"
                "目前以裝置時間判斷季節。）")
        return

    st.caption("點下方圖示，允許定位後背景會依你的城市與當地時間變化：")
    loc = streamlit_geolocation()
    if loc and loc.get("latitude") is not None:
        lat, lon = loc["latitude"], loc["longitude"]
        prev = st.session_state.get("_geo") or {}
        # 座標有變動才反查城市，避免每次重跑都打 API
        if prev.get("lat") != lat or prev.get("lon") != lon:
            city = _reverse_geocode(lat, lon)
            city_en = _reverse_geocode_en(lat, lon)
            st.session_state["_geo"] = {"lat": lat, "lon": lon,
                                        "city": city, "city_en": city_en}
            st.rerun()


@st.cache_data(show_spinner=False)
def _reverse_geocode(lat, lon):
    """用免費、免金鑰的 BigDataCloud API 把座標反查成城市名（中文）。失敗回空字串。"""
    try:
        import requests
        r = requests.get(
            "https://api.bigdatacloud.net/data/reverse-geocode-client",
            params={"latitude": lat, "longitude": lon, "localityLanguage": "zh"},
            timeout=6)
        j = r.json()
        return j.get("city") or j.get("locality") or j.get("principalSubdivision") or ""
    except Exception:
        return ""


@st.cache_data(show_spinner=False)
def _reverse_geocode_en(lat, lon):
    """另取英文城市名，給 Unsplash 搜尋用（英文關鍵字命中率較高）。"""
    try:
        import requests
        r = requests.get(
            "https://api.bigdatacloud.net/data/reverse-geocode-client",
            params={"latitude": lat, "longitude": lon, "localityLanguage": "en"},
            timeout=6)
        j = r.json()
        return j.get("city") or j.get("locality") or j.get("principalSubdivision") or ""
    except Exception:
        return ""


# 時段 → 英文關鍵字（給 Unsplash 搜尋；對應視覺氛圍）
PHASE_EN = {"morning": "sunrise morning", "day": "daytime street",
            "dusk": "sunset dusk", "night": "night cityscape lights"}


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_city_photo(city_en, phase, key):
    """用 Unsplash 依『城市 + 時段』搜尋一張橫向風景照，回傳圖片 URL。
    一小時內同樣的城市+時段會走快取(ttl=3600)，避免重複打 API。
    沒有金鑰或失敗時回傳 None（呼叫端會退回漸層背景）。"""
    if not key or not city_en:
        return None
    try:
        import requests
        query = f"{city_en} {PHASE_EN.get(phase, 'cityscape')}"
        r = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "orientation": "landscape", "per_page": 10},
            headers={"Authorization": f"Client-ID {key}"},
            timeout=8)
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        if not results:
            return None
        # 從前幾張裡隨機挑一張，達成你要的「每次隨機」效果
        import random
        pick = random.choice(results[:min(10, len(results))])
        return pick["urls"]["regular"]
    except Exception:
        return None


def get_unsplash_key():
    """從 Streamlit Secrets 讀 Unsplash 金鑰；沒設定就回 None（不報錯）。"""
    try:
        return st.secrets.get("UNSPLASH_ACCESS_KEY")
    except Exception:
        return None


def apply_theme(theme: str):
    """依選定主題注入 CSS。回傳一個 dict 供繪圖用（plotly 模板、漲跌色）。"""
    # 預設（深色金融儀表板，沿用 v1 風格）
    plot_template = "plotly_dark"
    up_color, down_color = "#3fb950", "#f85149"
    paper = "rgba(0,0,0,0)"

    if theme == "Dark":
        css = _css_dark()
    elif theme == "Light":
        css = _css_light()
        plot_template = "plotly_white"
    elif theme == "System":
        css = _css_system()
    elif theme == "新手友善版":
        css = _css_newbie()
        plot_template = "plotly_white"
        up_color, down_color = "#16a34a", "#dc2626"
    elif theme == "四季風景版":
        request_geolocation()
        season, phase, city, _ = detect_season_and_phase()
        g1, g2, text_col = SEASON_GRADIENTS[(season, phase)]
        dark_phase = phase == "night" or (season == "autumn" and phase == "dusk")
        plot_template = "plotly_dark" if dark_phase else "plotly_white"
        # 嘗試抓該城市+時段的真實風景照當背景；失敗則用漸層
        geo = st.session_state.get("_geo") or {}
        photo = fetch_city_photo(geo.get("city_en", ""), phase, get_unsplash_key())
        if photo:
            css = _css_season_photo(photo, dark_phase)
        else:
            css = _css_season(g1, g2, text_col, dark_phase)
        st.session_state["_season_info"] = (season, phase, city)
    else:
        css = _css_dark()

    st.markdown(css, unsafe_allow_html=True)
    return {"template": plot_template, "up": up_color,
            "down": down_color, "paper": paper}


def _base_fonts():
    return ("@import url('https://fonts.googleapis.com/css2?"
            "family=Lexend:wght@300;500;700&"
            "family=JetBrains+Mono:wght@500&"
            "family=Noto+Sans+TC:wght@400;500;700&display=swap');")


def _css_dark():
    return f"""<style>{_base_fonts()}
    .stApp {{ background:#0d1117; }}
    html,body,[class*="css"] {{ font-family:'Lexend','Noto Sans TC',sans-serif; color:#e6edf3; }}
    .main-title {{ font-size:2.1rem; font-weight:700; color:#f0f6fc; margin-bottom:0; }}
    .subtitle {{ color:#7d8590; font-size:.95rem; margin-top:.2rem; }}
    .metric-card {{ background:linear-gradient(145deg,#161b22,#1c2129);
      border:1px solid #30363d; border-radius:14px; padding:1.1rem 1.3rem; }}
    .metric-label {{ color:#7d8590; font-size:.8rem; text-transform:uppercase; letter-spacing:1px; }}
    .metric-value {{ font-family:'JetBrains Mono',monospace; font-size:1.7rem; color:#f0f6fc; margin-top:.2rem; }}
    .disclaimer {{ background:rgba(187,128,9,.12); border-left:3px solid #bb8009;
      padding:.7rem 1rem; border-radius:6px; color:#d9b25b; font-size:.85rem; }}
    </style>"""


def _force_text(color, muted, heading):
    """產生一段「強制把 Streamlit 內建元件文字都上色」的 CSS 片段。
    這是修正淺色/新手/四季版文字看不清的關鍵：Streamlit 的標題(h1~h6)、
    內文、選單標籤都有自己的 class，光設 body 顏色蓋不到，需用 !important 明確指定。
    color=主文字、muted=次要文字、heading=標題顏色。
    """
    return f"""
    /* 主內容區所有文字 */
    .stApp, .stApp p, .stApp li, .stApp span, .stApp label,
    .stMarkdown, .stMarkdown p, .stMarkdown li,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] span {{ color:{color} !important; }}
    /* 標題 h1~h6（st.subheader/st.header 都會變成這些） */
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
    [data-testid="stHeading"] {{ color:{heading} !important; }}
    /* 側邊欄文字 */
    section[data-testid="stSidebar"] * {{ color:{color} !important; }}
    /* 次要說明文字（st.caption） */
    [data-testid="stCaptionContainer"], .stApp small {{ color:{muted} !important; }}
    """


def _css_light():
    return f"""<style>{_base_fonts()}
    .stApp {{ background:#f6f8fa; }}
    html,body,[class*="css"] {{ font-family:'Lexend','Noto Sans TC',sans-serif; }}
    {_force_text("#1f2328", "#656d76", "#1f2328")}
    .main-title {{ font-size:2.1rem; font-weight:700; color:#1f2328 !important; margin-bottom:0; }}
    .subtitle {{ color:#656d76 !important; font-size:.95rem; margin-top:.2rem; }}
    .metric-card {{ background:#ffffff; border:1px solid #d0d7de; border-radius:14px;
      padding:1.1rem 1.3rem; box-shadow:0 1px 3px rgba(0,0,0,.06); }}
    .metric-label {{ color:#656d76 !important; font-size:.8rem; text-transform:uppercase; letter-spacing:1px; }}
    .metric-value {{ font-family:'JetBrains Mono',monospace; font-size:1.7rem; color:#1f2328 !important; margin-top:.2rem; }}
    .disclaimer {{ background:#fff8e1; border-left:3px solid #d4a72c;
      padding:.7rem 1rem; border-radius:6px; color:#7a5c00 !important; font-size:.9rem; line-height:1.7; }}
    .disclaimer * {{ color:#7a5c00 !important; }}
    </style>"""


def _css_system():
    # 跟隨作業系統深淺色：用 prefers-color-scheme
    return f"""<style>{_base_fonts()}
    html,body,[class*="css"] {{ font-family:'Lexend','Noto Sans TC',sans-serif; }}
    .main-title {{ font-size:2.1rem; font-weight:700; margin-bottom:0; }}
    .subtitle {{ font-size:.95rem; margin-top:.2rem; opacity:.7; }}
    .metric-card {{ border-radius:14px; padding:1.1rem 1.3rem; border:1px solid; }}
    .metric-label {{ font-size:.8rem; text-transform:uppercase; letter-spacing:1px; opacity:.6; }}
    .metric-value {{ font-family:'JetBrains Mono',monospace; font-size:1.7rem; margin-top:.2rem; }}
    .disclaimer {{ border-left:3px solid #d4a72c; padding:.7rem 1rem; border-radius:6px; font-size:.85rem; }}
    @media (prefers-color-scheme: dark) {{
      .stApp {{ background:#0d1117; }} html,body,[class*="css"] {{ color:#e6edf3; }}
      .metric-card {{ background:#161b22; border-color:#30363d; }}
      .disclaimer {{ background:rgba(187,128,9,.12); color:#d9b25b; }}
    }}
    @media (prefers-color-scheme: light) {{
      .stApp {{ background:#f6f8fa; }} html,body,[class*="css"] {{ color:#1f2328; }}
      .metric-card {{ background:#fff; border-color:#d0d7de; }}
      .disclaimer {{ background:#fff8e1; color:#7a5c00; }}
    }}
    </style>"""


def _css_newbie():
    # 乾淨、留白多、大字、柔和。給第一次看股市的人。文字加深、對比拉高。
    return f"""<style>{_base_fonts()}
    .stApp {{ background:#fbfcfe; }}
    html,body,[class*="css"] {{ font-family:'Noto Sans TC','Lexend',sans-serif; }}
    {_force_text("#1a202c", "#4a5568", "#1e4d8b")}
    .main-title {{ font-size:1.95rem; font-weight:700; color:#1e4d8b !important; margin-bottom:0; }}
    .subtitle {{ color:#4a5568 !important; font-size:1rem; margin-top:.3rem; }}
    .metric-card {{ background:#fff; border:1px solid #cbd5e0; border-radius:18px;
      padding:1.3rem 1.5rem; box-shadow:0 2px 10px rgba(30,77,139,.08); }}
    .metric-label {{ color:#4a5568 !important; font-size:.9rem; letter-spacing:.3px; }}
    .metric-value {{ font-size:1.9rem; font-weight:700; color:#1a202c !important; margin-top:.3rem; }}
    .disclaimer {{ background:#e7f0fb; border-left:4px solid #2b6cb0;
      padding:.95rem 1.15rem; border-radius:10px; color:#1c3d5e !important; font-size:.98rem; line-height:1.8; }}
    .disclaimer * {{ color:#1c3d5e !important; }}
    .newbie-tip {{ background:#e9f9ef; border:1px solid #9ae6b4; border-radius:14px;
      padding:1rem 1.2rem; margin:.5rem 0; color:#1c4532 !important; line-height:1.8; }}
    .newbie-tip * {{ color:#1c4532 !important; }}
    /* 展開元件(expander)標題也要看得清楚 */
    .stExpander summary, .stExpander summary * {{ color:#1a202c !important; }}
    </style>"""


def _css_season(g1, g2, text_col, dark_phase):
    # 卡片底色加深(0.72)讓文字更清楚；文字加陰影scrim避免融進背景
    card_bg = "rgba(15,19,28,.72)" if dark_phase else "rgba(255,255,255,.78)"
    border = "rgba(255,255,255,.25)" if dark_phase else "rgba(0,0,0,.12)"
    shadow = ("0 1px 6px rgba(0,0,0,.55)" if dark_phase
              else "0 1px 4px rgba(255,255,255,.7)")
    return f"""<style>{_base_fonts()}
    .stApp {{
      background:linear-gradient(135deg,{g1},{g2},{g1});
      background-size:400% 400%;
      animation:seasonShift 28s ease infinite;
    }}
    @keyframes seasonShift {{
      0% {{background-position:0% 50%;}}
      50% {{background-position:100% 50%;}}
      100% {{background-position:0% 50%;}}
    }}
    html,body,[class*="css"] {{ font-family:'Noto Sans TC','Lexend',sans-serif; }}
    {_force_text(text_col, text_col, text_col)}
    /* 在漸層上的文字統一加陰影，確保任何季節都看得清楚 */
    .stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp p,.stApp li,.stApp label,
    section[data-testid="stSidebar"] * {{ text-shadow:{shadow}; }}
    .main-title {{ font-size:2.1rem; font-weight:700; color:{text_col} !important; margin-bottom:0; }}
    .subtitle {{ color:{text_col} !important; opacity:.9; font-size:.95rem; margin-top:.2rem; }}
    .metric-card {{ background:{card_bg}; backdrop-filter:blur(14px);
      -webkit-backdrop-filter:blur(14px); border:1px solid {border};
      border-radius:16px; padding:1.1rem 1.3rem; }}
    .metric-card * {{ text-shadow:none; }}
    .metric-label {{ color:{text_col} !important; opacity:.8; font-size:.8rem; letter-spacing:1px; }}
    .metric-value {{ font-family:'JetBrains Mono',monospace; font-size:1.7rem; color:{text_col} !important; margin-top:.2rem; }}
    .disclaimer {{ background:{card_bg}; backdrop-filter:blur(10px); border-left:3px solid {text_col};
      padding:.7rem 1rem; border-radius:10px; color:{text_col} !important; font-size:.9rem; line-height:1.7; }}
    .disclaimer *, .newbie-tip * {{ text-shadow:none; color:{text_col} !important; }}
    .newbie-tip {{ background:{card_bg}; backdrop-filter:blur(10px); border:1px solid {border};
      border-radius:14px; padding:1rem 1.2rem; margin:.5rem 0; color:{text_col} !important; line-height:1.8; }}
    .season-badge {{ display:inline-block; background:{card_bg}; backdrop-filter:blur(8px);
      border:1px solid {border}; border-radius:30px; padding:.3rem 1rem; color:{text_col} !important;
      font-size:.9rem; margin-bottom:.4rem; }}
    .stExpander summary, .stExpander summary * {{ color:{text_col} !important; }}
    </style>"""


def _css_season_photo(photo_url, dark_phase):
    """真實城市風景照當全螢幕固定背景，疊一層半透明遮罩(scrim)讓文字清楚。
    夜晚時段用暗色遮罩 + 白字；白天用亮色遮罩 + 深字。卡片用毛玻璃。"""
    if dark_phase:
        scrim = "linear-gradient(rgba(10,12,20,.62), rgba(10,12,20,.72))"
        text_col = "#f5f7fa"
        card_bg = "rgba(15,19,28,.62)"
        border = "rgba(255,255,255,.22)"
        shadow = "0 1px 8px rgba(0,0,0,.7)"
    else:
        scrim = "linear-gradient(rgba(255,255,255,.55), rgba(255,255,255,.68))"
        text_col = "#1a2330"
        card_bg = "rgba(255,255,255,.72)"
        border = "rgba(0,0,0,.12)"
        shadow = "0 1px 4px rgba(255,255,255,.8)"
    return f"""<style>{_base_fonts()}
    .stApp {{
      background:{scrim}, url('{photo_url}');
      background-size:cover, cover;
      background-position:center center;
      background-attachment:fixed, fixed;
      background-repeat:no-repeat;
    }}
    html,body,[class*="css"] {{ font-family:'Noto Sans TC','Lexend',sans-serif; }}
    {_force_text(text_col, text_col, text_col)}
    .stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp p,.stApp li,.stApp label,
    section[data-testid="stSidebar"] * {{ text-shadow:{shadow}; }}
    .main-title {{ font-size:2.1rem; font-weight:700; color:{text_col} !important; margin-bottom:0; }}
    .subtitle {{ color:{text_col} !important; opacity:.92; font-size:.95rem; margin-top:.2rem; }}
    section[data-testid="stSidebar"] {{ background:{card_bg}; backdrop-filter:blur(14px); }}
    .metric-card {{ background:{card_bg}; backdrop-filter:blur(14px);
      -webkit-backdrop-filter:blur(14px); border:1px solid {border};
      border-radius:16px; padding:1.1rem 1.3rem; }}
    .metric-card * {{ text-shadow:none; }}
    .metric-label {{ color:{text_col} !important; opacity:.8; font-size:.8rem; letter-spacing:1px; }}
    .metric-value {{ font-family:'JetBrains Mono',monospace; font-size:1.7rem; color:{text_col} !important; margin-top:.2rem; }}
    .disclaimer {{ background:{card_bg}; backdrop-filter:blur(10px); border-left:3px solid {text_col};
      padding:.7rem 1rem; border-radius:10px; color:{text_col} !important; font-size:.9rem; line-height:1.7; }}
    .disclaimer *, .newbie-tip * {{ text-shadow:none; color:{text_col} !important; }}
    .newbie-tip {{ background:{card_bg}; backdrop-filter:blur(10px); border:1px solid {border};
      border-radius:14px; padding:1rem 1.2rem; margin:.5rem 0; color:{text_col} !important; line-height:1.8; }}
    .season-badge {{ display:inline-block; background:{card_bg}; backdrop-filter:blur(8px);
      border:1px solid {border}; border-radius:30px; padding:.3rem 1rem; color:{text_col} !important;
      font-size:.9rem; margin-bottom:.4rem; }}
    .stExpander summary, .stExpander summary * {{ color:{text_col} !important; }}
    </style>"""


# ============================================================
# 資料載入
# ============================================================
def dpath(name):
    """優先讀 data/ 下的檔；找不到再退回同層（向下相容 v1）。"""
    p = os.path.join(DATA_DIR, name)
    return p if os.path.exists(p) else name


@st.cache_data
def load_stock(filename):
    path = dpath(filename)
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df.dropna(subset=["Date"])


@st.cache_data
def load_csv(filename):
    path = dpath(filename)
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, encoding="utf-8-sig")


def get_last_updated():
    path = dpath("last_updated.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return None


def _pct_over(closes, n):
    """以往回第 n 個有效收盤為基準算到最新收盤的漲幅(%)。"""
    if len(closes) <= n:
        return None
    base = closes.iloc[-1 - n]
    if base == 0:
        return None
    return round((closes.iloc[-1] - base) / base * 100, 2)


def _live_perf(df, code):
    """彙總檔缺失時，直接從股價 df 現算各區間漲幅，回傳與彙總檔同欄位的 dict。"""
    if df is None or df.empty:
        return None
    closes = df.dropna(subset=["Close"])["Close"].reset_index(drop=True)
    if closes.empty:
        return None
    tmp = df.dropna(subset=["Close"]).copy()
    tmp["Date"] = pd.to_datetime(tmp["Date"], errors="coerce")
    yr = tmp["Date"].dt.year.max()
    yr_rows = tmp[tmp["Date"].dt.year == yr]
    ytd = None
    if not yr_rows.empty and yr_rows.iloc[0]["Close"]:
        ytd = round((closes.iloc[-1] - yr_rows.iloc[0]["Close"])
                    / yr_rows.iloc[0]["Close"] * 100, 2)
    return {
        "name": code, "close": round(float(closes.iloc[-1]), 2),
        "chg_prev_day": _pct_over(closes, 1), "chg_1w": _pct_over(closes, 5),
        "chg_1m": _pct_over(closes, 21), "chg_ytd": ytd, "chg_1y": _pct_over(closes, 252),
    }


def fmt_pct(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:+.2f}%"


def pct_color(v, up, down):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "#888"
    return up if v >= 0 else down


def no_data_notice(what="股價"):
    """資料尚未產生時的友善提示（取代原本一行紅字）。"""
    st.warning(f"⏳ 目前還沒有{what}資料。")
    st.markdown(
        "這通常表示**爬蟲還沒在線上跑過第一次**。請依下列任一方式產生資料：\n\n"
        "- **線上(建議)**：到 GitHub repo 的 **Actions** 分頁 → 「每日資料更新」→ "
        "**Run workflow**，跑完約 3–8 分鐘後資料會自動出現，網站會自動重整。\n"
        "- **本機**：依序執行 `python fetch_stock.py`、`python fetch_ptt.py`、"
        "`python analyze_sentiment.py`，產生的 CSV 會放進 `data/` 資料夾。\n\n"
        "（首次設定步驟詳見 README 第五節。本提示是正常流程，不是程式錯誤。）"
    )


# ============================================================
# 側邊欄
# ============================================================
with st.sidebar:
    st.header("⚙️ 控制面板")
    theme = st.selectbox(
        "🎨 介面主題",
        ["Dark", "Light", "System", "新手友善版", "四季風景版"],
        index=0,
        help="新手友善版：乾淨大字 + 股市用詞教學；四季風景版：依你所在地時間變換動態背景。",
    )
    st.divider()
    page = st.radio("📑 頁面", ["單一標的分析", "多標的比較", "市場總覽"])
    st.divider()

# 套用主題（要在畫任何元件前）
style = apply_theme(theme)

with st.sidebar:
    if page == "單一標的分析":
        target_name = st.selectbox("選擇標的", list(TARGETS.keys()))
        show_ma = st.checkbox("顯示移動平均線 (MA5/MA20)", value=True)
        show_volume = st.checkbox("顯示成交量", value=True)
        days = st.slider("顯示天數", 30, 500, 120)
    st.divider()
    lu = get_last_updated()
    st.caption(f"📅 資料更新於：{lu}" if lu else "📅 資料更新時間：未知")
    st.caption("來源：yfinance（股價）+ PTT Stock 板（輿情）")
    if theme == "四季風景版" and "_season_info" in st.session_state:
        s, p, city = st.session_state["_season_info"]
        loc = f"{city}· " if city else ""
        st.caption(f"目前情境：{loc}{SEASON_LABEL[s]} · {PHASE_LABEL[p]}（依你所在城市與時間）")


# ============================================================
# 共用標題
# ============================================================
def header():
    if theme == "四季風景版" and "_season_info" in st.session_state:
        s, p, city = st.session_state["_season_info"]
        loc = f"{city} · " if city else ""
        st.markdown(f'<span class="season-badge">📍 {loc}{SEASON_LABEL[s]} · {PHASE_LABEL[p]} 情境背景</span>',
                    unsafe_allow_html=True)
    st.markdown('<p class="main-title">📊 台美股輿情 × 量化趨勢分析</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">整合社群輿情情緒與技術指標的 ETF 趨勢分析系統 · 專題 v2</p>',
                unsafe_allow_html=True)
    st.write("")


# ============================================================
# 頁面 1：單一標的分析
# ============================================================
def page_single():
    header()
    stock = load_stock(TARGETS[target_name][0])
    if stock is None:
        no_data_notice(f"「{target_name}」的股價")
        st.stop()

    code = TARGETS[target_name][1]
    full = stock.copy()
    stock = stock.tail(days).reset_index(drop=True)
    latest = stock.dropna(subset=["Close"]).iloc[-1]
    prev = stock.dropna(subset=["Close"]).iloc[-2] if len(stock) > 1 else latest
    change = latest["Close"] - prev["Close"]
    change_pct = (change / prev["Close"] * 100) if prev["Close"] else 0

    # 區間漲幅（優先讀彙總檔；取不到就用本檔股價現算，確保有資料就有數值）
    perf = load_csv("performance_summary.csv")
    prow = None
    if perf is not None:
        clean = perf["ticker"].astype(str).str.replace(".", "_", regex=False)
        m = perf[clean.str.fullmatch(f"{code}(_TW)?", case=False, na=False)]
        if not m.empty:
            prow = m.iloc[0].to_dict()
    if prow is None:
        # 彙總檔缺失 → 直接用目前載入的整段股價現算各區間漲幅
        prow = _live_perf(full, code)

    # 對應標的的輿情（優先用分標的檔）
    by_tgt = load_csv("daily_sentiment_by_target.csv")
    daily_sent = load_csv("daily_sentiment.csv")
    if by_tgt is not None and "target" in by_tgt.columns:
        sub = by_tgt[by_tgt["target"].astype(str) == code]
        avg_sent = sub["avg_sentiment"].mean() if not sub.empty else None
        sent_series = sub
    else:
        avg_sent = daily_sent["avg_sentiment"].mean() if daily_sent is not None else None
        sent_series = daily_sent

    # ---- 指標卡 ----
    c1, c2, c3, c4 = st.columns(4)
    color = style["up"] if change >= 0 else style["down"]
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
        sent_txt = f"{avg_sent:+.2f}" if avg_sent is not None and pd.notna(avg_sent) else "—"
        sent_color = style["up"] if (avg_sent or 0) >= 0 else style["down"]
        st.markdown(f'<div class="metric-card"><div class="metric-label">PTT 輿情情緒</div>'
                    f'<div class="metric-value" style="color:{sent_color}">{sent_txt}</div></div>',
                    unsafe_allow_html=True)
    st.write("")

    # ---- 區間漲幅列 ----
    st.subheader("📐 區間漲幅")
    labels = [("前一交易日", "chg_prev_day"), ("近一週", "chg_1w"),
              ("近一月", "chg_1m"), ("今年以來", "chg_ytd"), ("近一年", "chg_1y")]
    cols = st.columns(5)
    for (lab, key), col in zip(labels, cols):
        v = float(prow[key]) if prow is not None and pd.notna(prow.get(key)) else None
        with col:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{lab}</div>'
                        f'<div class="metric-value" style="color:{pct_color(v, style["up"], style["down"])}">'
                        f'{fmt_pct(v)}</div></div>', unsafe_allow_html=True)
    st.write("")

    # ---- 股價圖 ----
    st.subheader(f"📈 {target_name} 走勢")
    rows = 2 if show_volume else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        row_heights=[0.72, 0.28] if show_volume else [1],
                        vertical_spacing=0.04)
    fig.add_trace(go.Candlestick(
        x=stock["Date"], open=stock["Open"], high=stock["High"],
        low=stock["Low"], close=stock["Close"], name="價格",
        increasing_line_color=style["up"], decreasing_line_color=style["down"]),
        row=1, col=1)
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
    fig.update_layout(template=style["template"], height=520,
                      paper_bgcolor=style["paper"], plot_bgcolor=style["paper"],
                      xaxis_rangeslider_visible=False,
                      legend=dict(orientation="h", y=1.08), margin=dict(t=30, b=10))
    st.plotly_chart(fig, width='stretch')

    # ---- RSI ----
    if "RSI14" in stock:
        st.subheader("📉 RSI(14) 相對強弱指標")
        rfig = go.Figure()
        rfig.add_trace(go.Scatter(x=stock["Date"], y=stock["RSI14"], name="RSI",
                                  line=dict(color="#bc8cff", width=1.6)))
        rfig.add_hline(y=70, line_dash="dash", line_color=style["down"], annotation_text="超買 70")
        rfig.add_hline(y=30, line_dash="dash", line_color=style["up"], annotation_text="超賣 30")
        rfig.update_layout(template=style["template"], height=260,
                           paper_bgcolor=style["paper"], plot_bgcolor=style["paper"],
                           margin=dict(t=20, b=10), yaxis_range=[0, 100])
        st.plotly_chart(rfig, width='stretch')

    # ---- 輿情 ----
    st.subheader("💬 PTT 輿情情緒分析")
    if sent_series is not None and not sent_series.empty and "avg_sentiment" in sent_series:
        sfig = go.Figure()
        xcol = "day" if "day" in sent_series else sent_series.columns[0]
        colors = [style["up"] if v >= 0 else style["down"] for v in sent_series["avg_sentiment"]]
        sfig.add_trace(go.Bar(x=sent_series[xcol], y=sent_series["avg_sentiment"],
                              marker_color=colors, name="每日情緒"))
        sfig.update_layout(template=style["template"], height=300, title="每日綜合情緒分數",
                           paper_bgcolor=style["paper"], plot_bgcolor=style["paper"],
                           margin=dict(t=40, b=10))
        st.plotly_chart(sfig, width='stretch')
    else:
        st.info("尚無此標的的每日情緒資料，請先執行 analyze_sentiment.py")

    # ---- 趨勢傾向 ----
    render_verdict(latest, stock, avg_sent)


def render_verdict(latest, stock, avg_sent):
    st.subheader("🧭 趨勢傾向判斷")
    if theme == "新手友善版":
        st.markdown(f'<div class="disclaimer">{VERDICT_EXPLAIN}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="disclaimer">⚠️ 以下為<b>規則版示意判斷</b>，'
                    '結合 RSI、均線與當前輿情情緒方向綜合給出傾向。'
                    '正式機器學習預測模型需累積數月輿情資料後訓練，為本專題後續開發項目。</div>',
                    unsafe_allow_html=True)
    st.write("")

    rsi = latest.get("RSI14", float("nan"))
    signals, score = [], 0
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
    if avg_sent is not None and pd.notna(avg_sent):
        if avg_sent > 0.1:
            signals.append(f"PTT 輿情偏正面（{avg_sent:+.2f}），市場情緒樂觀"); score += 1
        elif avg_sent < -0.1:
            signals.append(f"PTT 輿情偏負面（{avg_sent:+.2f}），市場情緒悲觀"); score -= 1
        else:
            signals.append("PTT 輿情中性")

    verdict = ("偏多 📈", style["up"]) if score > 0 else \
              (("偏空 📉", style["down"]) if score < 0 else ("中性 ⚖️", "#d29922"))
    st.markdown(f"### 綜合傾向：<span style='color:{verdict[1]}'>{verdict[0]}</span>",
                unsafe_allow_html=True)
    for s in signals:
        st.markdown(f"- {s}")

    # 新手友善版：附上股市用詞教學
    if theme == "新手友善版":
        st.write("")
        st.subheader("📚 股市用詞小教室")
        st.caption("第一次看股市？這裡用白話解釋上面出現的名詞。")
        for term, desc in GLOSSARY:
            with st.expander(f"❓ {term}"):
                st.markdown(f'<div class="newbie-tip">{desc}</div>', unsafe_allow_html=True)

    st.write("")
    st.caption("本系統為學術專題用途，所有內容僅供研究參考，不構成任何投資建議。")


# ============================================================
# 頁面 2：多標的比較
# ============================================================
def page_compare():
    header()
    st.subheader("📊 多標的區間漲幅比較")
    perf = load_csv("performance_summary.csv")
    if perf is None or perf.empty:
        no_data_notice("多標的比較所需的")
        st.stop()

    label_map = {"chg_prev_day": "前一交易日", "chg_1w": "近一週", "chg_1m": "近一月",
                 "chg_ytd": "今年以來", "chg_1y": "近一年"}
    period = st.radio("選擇比較區間", list(label_map.values()), horizontal=True)
    key = [k for k, v in label_map.items() if v == period][0]

    perf = perf.copy()
    perf["val"] = pd.to_numeric(perf[key], errors="coerce")
    perf_sorted = perf.sort_values("val", ascending=False)

    # 橫向長條圖：紅綠分明
    bfig = go.Figure()
    colors = [style["up"] if v >= 0 else style["down"] for v in perf_sorted["val"]]
    bfig.add_trace(go.Bar(
        x=perf_sorted["val"], y=perf_sorted["name"], orientation="h",
        marker_color=colors,
        text=[fmt_pct(v) for v in perf_sorted["val"]], textposition="auto"))
    bfig.update_layout(template=style["template"], height=380,
                       title=f"各標的「{period}」漲跌幅 (%)",
                       paper_bgcolor=style["paper"], plot_bgcolor=style["paper"],
                       margin=dict(t=50, b=10), xaxis_title="漲跌幅 %")
    st.plotly_chart(bfig, width='stretch')

    # 完整對照表
    st.subheader("📋 完整區間漲幅對照表")
    show = perf[["name", "close", "chg_prev_day", "chg_1w", "chg_1m", "chg_ytd", "chg_1y", "rsi14"]].copy()
    show.columns = ["標的", "收盤", "前一日", "近一週", "近一月", "今年以來", "近一年", "RSI"]
    st.dataframe(show, width='stretch', hide_index=True)

    if theme == "新手友善版":
        st.markdown('<div class="disclaimer">💡 怎麼看這張表：每一欄是「相對那個時間點到現在」的漲跌百分比。'
                    '例如「近一年 +20%」代表一年前買入到現在大約上漲兩成。綠色為上漲、紅色為下跌。'
                    '不同 ETF 性質不同（高股息 vs 市值型），短期漲幅不代表優劣。</div>',
                    unsafe_allow_html=True)
    st.write("")
    st.caption("本系統為學術專題用途，所有內容僅供研究參考，不構成任何投資建議。")


# ============================================================
# 頁面 3：市場總覽（參考 twetf 的總覽概念）
# ============================================================
def page_overview():
    header()
    st.subheader("🗺️ 市場總覽")
    perf = load_csv("performance_summary.csv")
    daily_sent = load_csv("daily_sentiment.csv")

    if perf is not None and not perf.empty:
        perf = perf.copy()
        perf["d"] = pd.to_numeric(perf["chg_prev_day"], errors="coerce")
        up_cnt = int((perf["d"] > 0).sum())
        down_cnt = int((perf["d"] < 0).sum())
        best = perf.loc[perf["d"].idxmax()] if perf["d"].notna().any() else None
        worst = perf.loc[perf["d"].idxmin()] if perf["d"].notna().any() else None
        avg_sent = daily_sent["avg_sentiment"].mean() if daily_sent is not None else None

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">監控標的</div>'
                        f'<div class="metric-value">{len(perf)}</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">今日上漲 / 下跌</div>'
                        f'<div class="metric-value"><span style="color:{style["up"]}">{up_cnt}</span>'
                        f' / <span style="color:{style["down"]}">{down_cnt}</span></div></div>',
                        unsafe_allow_html=True)
        with c3:
            if best is not None:
                st.markdown(f'<div class="metric-card"><div class="metric-label">今日最強</div>'
                            f'<div class="metric-value" style="color:{style["up"]};font-size:1.2rem">'
                            f'{best["name"]}<br>{fmt_pct(best["d"])}</div></div>', unsafe_allow_html=True)
        with c4:
            s_txt = f"{avg_sent:+.2f}" if avg_sent is not None and pd.notna(avg_sent) else "—"
            s_col = style["up"] if (avg_sent or 0) >= 0 else style["down"]
            st.markdown(f'<div class="metric-card"><div class="metric-label">全市場輿情</div>'
                        f'<div class="metric-value" style="color:{s_col}">{s_txt}</div></div>',
                        unsafe_allow_html=True)
        st.write("")

        # 全標的「今年以來」漲幅一覽
        st.subheader("📈 各標的今年以來表現")
        perf["ytd"] = pd.to_numeric(perf["chg_ytd"], errors="coerce")
        ps = perf.sort_values("ytd", ascending=True)
        ofig = go.Figure()
        ofig.add_trace(go.Bar(
            x=ps["ytd"], y=ps["name"], orientation="h",
            marker_color=[style["up"] if v >= 0 else style["down"] for v in ps["ytd"]],
            text=[fmt_pct(v) for v in ps["ytd"]], textposition="auto"))
        ofig.update_layout(template=style["template"], height=340,
                           paper_bgcolor=style["paper"], plot_bgcolor=style["paper"],
                           margin=dict(t=20, b=10), xaxis_title="今年以來 %")
        st.plotly_chart(ofig, width='stretch')
    else:
        no_data_notice("市場總覽所需的")

    # 全市場每日情緒
    if daily_sent is not None and not daily_sent.empty:
        st.subheader("💬 全市場每日輿情情緒")
        sfig = go.Figure()
        colors = [style["up"] if v >= 0 else style["down"] for v in daily_sent["avg_sentiment"]]
        sfig.add_trace(go.Bar(x=daily_sent["day"], y=daily_sent["avg_sentiment"], marker_color=colors))
        sfig.update_layout(template=style["template"], height=300,
                           paper_bgcolor=style["paper"], plot_bgcolor=style["paper"],
                           margin=dict(t=20, b=10))
        st.plotly_chart(sfig, width='stretch')

    st.write("")
    st.caption("本系統為學術專題用途，所有內容僅供研究參考，不構成任何投資建議。")


# ============================================================
# 路由
# ============================================================
if page == "單一標的分析":
    page_single()
elif page == "多標的比較":
    page_compare()
else:
    page_overview()
