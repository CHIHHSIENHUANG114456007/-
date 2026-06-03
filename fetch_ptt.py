"""
fetch_ptt.py — PTT 股板輿情採集（v2）
專題：整合社群輿情與量化指標之台美股 ETF 趨勢預測系統

v2 變更：
    1. 關鍵字擴充，涵蓋 6 檔核心精選標的（0050 / 0056 / 00878 / 00919 / 2330 / TSM）。
    2. 輸出到 data/ptt_stock.csv，配合 GitHub Actions 自動 commit。
    3. 標的標記：每篇文章標出命中哪些標的，方便後續做「分標的情緒」。

執行方式（本機或 GitHub Actions）：
    pip install requests beautifulsoup4 pandas
    python fetch_ptt.py

重要備註：
    1. 沙箱網路受限無法連 PTT，請在本機 / GitHub Actions 執行。
    2. 已內建請求延遲與 User-Agent，為禮貌爬蟲（對應 SWOT 的反爬機制威脅），
       請勿把 DELAY_SEC 改太短。
    3. 若 PTT 改版導致解析失敗，需更新下方 CSS selector。
"""

import os
import sys
import time
import re
import pandas as pd

BASE = "https://www.ptt.cc"
BOARD = "Stock"
PAGES_TO_CRAWL = int(os.environ.get("PAGES_TO_CRAWL", "5"))  # 可用環境變數覆蓋
DELAY_SEC = 1.0
DATA_DIR = "data"

# v2 標的關鍵字對照：命中任一別名即視為與該標的相關
TARGET_KEYWORDS = {
    "0050":  ["0050", "台灣50", "元大台灣五十"],
    "0056":  ["0056", "高股息", "元大高股息"],
    "00878": ["00878", "國泰永續", "永續高股息"],
    "00919": ["00919", "群益台灣精選", "精選高息"],
    "2330":  ["2330", "台積", "tsmc", "護國神山"],
    "TSM":   ["tsm", "台積電adr", "台積adr"],
}
ALL_KEYWORDS = [k.lower() for ks in TARGET_KEYWORDS.values() for k in ks]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0 Safari/537.36")
}
COOKIES = {"over18": "1"}


def get_session():
    try:
        import requests
    except ImportError:
        print("  [錯誤] 尚未安裝 requests，請先執行：pip install requests beautifulsoup4")
        sys.exit(1)
    s = requests.Session()
    s.headers.update(HEADERS)
    s.cookies.update(COOKIES)
    return s


def parse_push(soup_article) -> tuple[int, int]:
    pushes = soup_article.find_all("div", class_="push")
    up = sum(1 for p in pushes if p.find("span", class_="push-tag")
             and "推" in p.find("span", class_="push-tag").text)
    down = sum(1 for p in pushes if p.find("span", class_="push-tag")
               and "噓" in p.find("span", class_="push-tag").text)
    return up, down


def matched_targets(text: str) -> list[str]:
    """回傳這段文字命中了哪些標的代號。"""
    low = text.lower()
    hit = []
    for code, aliases in TARGET_KEYWORDS.items():
        if any(a.lower() in low for a in aliases):
            hit.append(code)
    return hit


def crawl():
    from bs4 import BeautifulSoup
    os.makedirs(DATA_DIR, exist_ok=True)
    s = get_session()

    print("=" * 60)
    print(f"PTT {BOARD} 板輿情採集 v2 — 抓 {PAGES_TO_CRAWL} 頁")
    print("=" * 60)

    index_url = f"{BASE}/bbs/{BOARD}/index.html"
    try:
        r = s.get(index_url, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"  [錯誤] 連線 PTT 失敗：{e!r}")
        print("  請確認網路，或 PTT 是否更新了反爬機制。")
        return

    soup = BeautifulSoup(r.text, "html.parser")
    article_links = []
    for _ in range(PAGES_TO_CRAWL):
        for ent in soup.select("div.r-ent div.title a"):
            article_links.append(BASE + ent["href"])
        prev = [a for a in soup.select("div.btn-group-paging a") if "上頁" in a.text]
        if not prev:
            break
        time.sleep(DELAY_SEC)
        soup = BeautifulSoup(s.get(BASE + prev[0]["href"], timeout=10).text, "html.parser")

    print(f"  共蒐集到 {len(article_links)} 篇文章連結，開始逐篇解析...")
    rows = []
    for i, link in enumerate(article_links, 1):
        try:
            time.sleep(DELAY_SEC)
            art = BeautifulSoup(s.get(link, timeout=10).text, "html.parser")

            title, date = "", ""
            for line in art.select("div.article-metaline"):
                tag = line.select_one("span.article-meta-tag")
                val = line.select_one("span.article-meta-value")
                if not tag or not val:
                    continue
                if "標題" in tag.text.strip():
                    title = val.text.strip()
                elif "時間" in tag.text.strip():
                    date = val.text.strip()

            if not date:
                m = re.search(r"/M\.(\d{10})\.", link)
                if m:
                    date = time.strftime("%a %b %d %H:%M:%S %Y",
                                         time.localtime(int(m.group(1))))

            body = art.select_one("#main-content")
            text = body.text if body else ""
            hits = matched_targets(title + text)
            if not hits:
                continue

            up, down = parse_push(art)
            rows.append({
                "title": title,
                "date": date,
                "push": up,
                "boo": down,
                "score": up - down,
                "targets": ",".join(hits),   # v2：標出相關標的
                "url": link,
                "body": re.sub(r"\s+", " ", text)[:500],
            })
        except Exception as e:
            print(f"  [略過] 第 {i} 篇解析失敗：{e!r}")

    if not rows:
        print("\n❌ 沒有抓到相關文章（關鍵字太嚴、被限流、或頁面改版）。")
        return

    df = pd.DataFrame(rows)
    out = os.path.join(DATA_DIR, "ptt_stock.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print("\n" + "=" * 60)
    print(f"✅ 可行：抓到 {len(df)} 篇相關文章，已存成 {out}")
    print(f"   平均推文：{df['push'].mean():.1f}  平均噓文：{df['boo'].mean():.1f}")
    print("   下一步：python analyze_sentiment.py")
    print("=" * 60)


if __name__ == "__main__":
    crawl()
