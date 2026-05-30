"""
fetch_ptt.py — PTT 股板輿情採集與可行性驗證腳本
專題：整合社群輿情與量化指標之台美股 ETF 趨勢預測系統

用途：
    抓取 PTT Stock 板文章標題、時間、推噓數、內文，
    並用關鍵字過濾出與 0050 / 台積電 相關的討論，輸出 CSV 供情緒分析使用。

執行方式（在你自己的電腦上）：
    pip install requests beautifulsoup4 pandas
    python fetch_ptt.py

重要備註：
    1. 本腳本在受限網路沙箱中無法連外，請在本機執行。
    2. PTT 是公開看板，但請遵守 robots.txt 與合理抓取頻率（已內建延遲）。
       這呼應你們 SWOT 的「反爬機制」威脅 — 故意放慢速度、設 User-Agent。
    3. PTT 部分看板需點選「已滿18歲」按鈕；Stock 板不需要，
       但程式仍帶上 over18 cookie 以策安全。
"""

import sys
import time
import re
import pandas as pd

BASE = "https://www.ptt.cc"
BOARD = "Stock"          # 股板
PAGES_TO_CRAWL = 3       # 先抓最新 3 頁驗證可行性，正式採集再加大
DELAY_SEC = 1.0          # 每次請求間隔，禮貌爬蟲

# 與本專題標的相關的關鍵字（命中才保留）
KEYWORDS = ["0050", "台積", "2330", "tsmc", "tsm", "護國神山", "權值"]

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
    """從文章頁解析推/噓數量。回傳 (推, 噓)。"""
    pushes = soup_article.find_all("div", class_="push")
    up = sum(1 for p in pushes if p.find("span", class_="push-tag")
             and "推" in p.find("span", class_="push-tag").text)
    down = sum(1 for p in pushes if p.find("span", class_="push-tag")
               and "噓" in p.find("span", class_="push-tag").text)
    return up, down


def crawl():
    from bs4 import BeautifulSoup
    s = get_session()

    print("=" * 60)
    print(f"PTT {BOARD} 板輿情採集 — 可行性驗證")
    print("=" * 60)

    # 先取得看板首頁，找出「上一頁」連結往回翻
    index_url = f"{BASE}/bbs/{BOARD}/index.html"
    rows = []
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
        prev = [a for a in soup.select("div.btn-group-paging a")
                if "上頁" in a.text]
        if not prev:
            break
        time.sleep(DELAY_SEC)
        soup = BeautifulSoup(s.get(BASE + prev[0]["href"], timeout=10).text,
                             "html.parser")

    print(f"  共蒐集到 {len(article_links)} 篇文章連結，開始逐篇解析...")

    for i, link in enumerate(article_links, 1):
        try:
            time.sleep(DELAY_SEC)
            art = BeautifulSoup(s.get(link, timeout=10).text, "html.parser")

            # 用「標籤名稱」配對抓 meta，避免欄位順序變動造成錯位。
            # PTT meta 結構：每行有 article-meta-tag(作者/標題/時間) + article-meta-value
            title, date = "", ""
            for line in art.select("div.article-metaline"):
                tag = line.select_one("span.article-meta-tag")
                val = line.select_one("span.article-meta-value")
                if not tag or not val:
                    continue
                tag_text = tag.text.strip()
                if "標題" in tag_text:
                    title = val.text.strip()
                elif "時間" in tag_text:
                    date = val.text.strip()

            # 備援：若 meta 沒抓到時間，從網址的時間戳推算
            # PTT 網址格式 .../M.1739161234.A.xxx.html，數字為 unix 秒數
            if not date:
                m = re.search(r"/M\.(\d{10})\.", link)
                if m:
                    date = time.strftime("%a %b %d %H:%M:%S %Y",
                                         time.localtime(int(m.group(1))))

            # 關鍵字過濾：標題或內文命中本專題標的才保留
            body = art.select_one("#main-content")
            text = body.text if body else ""
            if not any(k in (title + text).lower() for k in KEYWORDS):
                continue

            up, down = parse_push(art)
            rows.append({
                "title": title,
                "date": date,
                "push": up,
                "boo": down,
                "score": up - down,          # 簡易輿情強度
                "url": link,
                "body": re.sub(r"\s+", " ", text)[:500],  # 留前 500 字
            })
        except Exception as e:
            print(f"  [略過] 第 {i} 篇解析失敗：{e!r}")

    if not rows:
        print("\n❌ 沒有抓到相關文章。可能原因：關鍵字太嚴、被限流、或頁面結構改版。")
        return

    df = pd.DataFrame(rows)
    df.to_csv("ptt_stock.csv", index=False, encoding="utf-8-sig")
    print("\n" + "=" * 60)
    print(f"✅ 可行：抓到 {len(df)} 篇與標的相關文章，已存成 ptt_stock.csv")
    print(f"   平均推文：{df['push'].mean():.1f}  平均噓文：{df['boo'].mean():.1f}")
    print("   下一步：把 body 餵入中文情緒模型，產生每日情緒分數，")
    print("           再與 stock_*.csv 依日期合併成訓練特徵。")
    print("=" * 60)


if __name__ == "__main__":
    crawl()
