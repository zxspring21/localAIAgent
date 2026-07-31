#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股「今年以來高點 -> 現在」跌幅最大股票掃描器
================================================

邏輯：
1. 用 TWSE 官方每日收盤行情 API（MI_INDEX，上市）抓「今年以來」每個交易日
   的全市場資料（代號、收盤價、最高價、成交量），逐日累加算出：
     - 今年至今最高價 (year_high)
     - 最新收盤價 (latest_close)
     - 最新成交量 (latest_volume，用來過濾流動性太差的股票)
2. 算出跌幅 % = (year_high - latest_close) / year_high * 100
3. 排除：
     - ETF / 權證 / 存託憑證等代號（非一般個股）
     - 成交量太小、流動性太差的股票（避免冷門股雜訊）
4. 先取跌幅最大的前 30 檔候選
5. 只對這 30 檔，用 FinMind 免費 API 補查「最近月營收年增率」，
   排除年增率嚴重衰退（例如 < -20%）的股票 —— 這類本業真的在惡化，
   跌是「有理由」，不算「錯殺」
6. 剩下的取跌幅最大前 10 檔輸出

⚠️ 重要說明（請務必閱讀）：
- 這支腳本只是「跌幅 + 簡單基本面過濾」的量化篩選器，不是「錯殺」的
  精確判斷。真正是否「錯殺」還需要你自己看：是否為短期消息面錯殺
  （例如單一客戶砍單被過度解讀）、公司體質、產業位置、法人籌碼等。
  請把輸出結果當作「候選名單」，不是投資建議。
- 本腳本只掃描「上市」(TWSE)，未含「上櫃」(TPEx)。如果你也要涵蓋上櫃，
  可以比照 fetch_twse_day() 的邏輯改寫一個 fetch_tpex_day()（TPEx的
  每日行情 API 網址與日期格式不同，是民國年格式）。
- TWSE 官方 API 對頻繁請求有基本限制，腳本內建 sleep，請不要調短。
- FinMind 免費額度有限（未帶 token 約 300 次/小時），本腳本只對前 30
  檔候選查詢，用量很小；如需更高額度可到 https://finmind.github.io/
  申請 token 並填入 FINMIND_TOKEN。

使用方式：
    pip install requests
    python tw_oversold_scanner.py

輸出：
    - 終端機列印前 10 檔
    - 同目錄下產生 tw_oversold_result.csv
"""

import requests
import time
import datetime
import csv
import sys

# ---------- 設定 ----------
YEAR_START = datetime.date(datetime.date.today().year, 1, 1)
TODAY = datetime.date.today()
SLEEP_SEC = 1.0          # 每次打 TWSE API 之間的間隔，避免被擋
MIN_AVG_VALUE_NTD = 5_000_000   # 最新一日成交金額至少要有這個門檻（新台幣元），過濾冷門股
CANDIDATE_POOL = 30       # 先取跌幅最大的前幾檔做基本面複查
TOP_N = 10                # 最終要幾檔
FINMIND_TOKEN = ""        # 如果有 FinMind token，填在這裡（可留空）

# 排除代號規則：ETF 通常 00 開頭（例如 0050, 00878...），存託憑證 / 特殊代號也排除
def is_normal_stock(code: str) -> bool:
    if not code.isdigit():
        return False
    if code.startswith("00"):   # ETF / 指數股票型基金
        return False
    if len(code) != 4:          # 一般個股是4碼；權證、其他衍生商品碼數不同
        return False
    return True


def fetch_twse_day(date: datetime.date):
    """抓 TWSE 單日全市場收盤行情 (上市)。回傳 list of dict，失敗或非交易日回傳 []"""
    date_str = date.strftime("%Y%m%d")
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
    params = {"date": date_str, "type": "ALL", "response": "json"}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
    except Exception as e:
        print(f"  [警告] {date_str} 抓取失敗: {e}", file=sys.stderr)
        return []

    if data.get("stat") != "OK":
        return []  # 非交易日或無資料

    # MI_INDEX 回傳裡，個股資料通常在 data["tables"] 的其中一個 table，
    # 欄位名稱包含 "證券代號", "證券名稱", "收盤價", "最高價", "成交股數" 等
    rows = []
    for table in data.get("tables", []):
        fields = table.get("fields", [])
        if "證券代號" not in fields or "收盤價" not in fields:
            continue
        idx = {name: i for i, name in enumerate(fields)}
        for r in table.get("data", []):
            try:
                code = r[idx["證券代號"]].strip()
                name = r[idx["證券名稱"]].strip()
                close = r[idx["收盤價"]].replace(",", "").strip()
                high = r[idx["最高價"]].replace(",", "").strip()
                volume_shares = r[idx["成交股數"]].replace(",", "").strip()
                if close in ("--", "") or high in ("--", ""):
                    continue
                rows.append({
                    "code": code,
                    "name": name,
                    "close": float(close),
                    "high": float(high),
                    "volume_shares": float(volume_shares) if volume_shares not in ("--", "") else 0.0,
                })
            except (KeyError, ValueError, IndexError):
                continue
    return rows


def scan_year_high_drawdown():
    """逐日掃描今年以來所有交易日，回傳 {code: {name, year_high, latest_close, latest_value}}"""
    stats = {}
    d = YEAR_START
    trading_days_found = 0
    while d <= TODAY:
        if d.weekday() < 5:  # 只嘗試平日，週末必為非交易日
            rows = fetch_twse_day(d)
            if rows:
                trading_days_found += 1
                for r in rows:
                    if not is_normal_stock(r["code"]):
                        continue
                    rec = stats.setdefault(r["code"], {
                        "name": r["name"],
                        "year_high": 0.0,
                        "latest_close": None,
                        "latest_value_ntd": 0.0,
                    })
                    if r["high"] > rec["year_high"]:
                        rec["year_high"] = r["high"]
                    # 因為是照日期順序往前掃，最後一次寫入的就是最新一個交易日的收盤價
                    rec["latest_close"] = r["close"]
                    rec["latest_value_ntd"] = r["close"] * r["volume_shares"]
            time.sleep(SLEEP_SEC)
        d += datetime.timedelta(days=1)

    print(f"共掃描到 {trading_days_found} 個交易日的資料", file=sys.stderr)
    return stats


def check_revenue_yoy(stock_id: str):
    """用 FinMind 查最近一筆月營收年增率，回傳 float 或 None（查不到）"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": stock_id,
        "start_date": (TODAY - datetime.timedelta(days=400)).strftime("%Y-%m-%d"),
    }
    if FINMIND_TOKEN:
        params["token"] = FINMIND_TOKEN
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json().get("data", [])
        if not data:
            return None
        data.sort(key=lambda x: x["revenue_month"], reverse=False)
        latest = data[-1]
        yoy = latest.get("revenue_year_growth_ratio") or latest.get("YoY") or None
        if yoy is None and "revenue" in latest:
            # 部分版本欄位名稱不同，嘗試自行用去年同月比較
            same_month_last_year = [
                x for x in data
                if x.get("revenue_year") == latest.get("revenue_year", 0) - 1
                and x.get("revenue_month") == latest.get("revenue_month")
            ]
            if same_month_last_year and same_month_last_year[0]["revenue"] > 0:
                yoy = (latest["revenue"] - same_month_last_year[0]["revenue"]) / same_month_last_year[0]["revenue"] * 100
        return yoy
    except Exception as e:
        print(f"  [警告] {stock_id} 營收查詢失敗: {e}", file=sys.stderr)
        return None


def main():
    print("開始掃描 TWSE 上市個股（今年以來每日行情）...這會花幾分鐘，請耐心等待", file=sys.stderr)
    stats = scan_year_high_drawdown()

    candidates = []
    for code, rec in stats.items():
        if rec["latest_close"] is None or rec["year_high"] <= 0:
            continue
        if rec["latest_value_ntd"] < MIN_AVG_VALUE_NTD:
            continue  # 流動性太差
        drawdown_pct = (rec["year_high"] - rec["latest_close"]) / rec["year_high"] * 100
        if drawdown_pct <= 0:
            continue
        candidates.append({
            "code": code,
            "name": rec["name"],
            "year_high": rec["year_high"],
            "latest_close": rec["latest_close"],
            "drawdown_pct": drawdown_pct,
        })

    candidates.sort(key=lambda x: x["drawdown_pct"], reverse=True)
    pool = candidates[:CANDIDATE_POOL]

    print(f"\n跌幅最大前 {CANDIDATE_POOL} 檔候選，開始查營收年增率做基本面過濾...", file=sys.stderr)
    final_list = []
    for c in pool:
        yoy = check_revenue_yoy(c["code"])
        c["revenue_yoy_pct"] = yoy
        # 過濾條件：查不到營收資料就保留（不確定不排除），
        # 若查得到且年增率 < -20%，視為本業明顯惡化，不算錯殺
        if yoy is not None and yoy < -20:
            continue
        final_list.append(c)
        time.sleep(0.3)

    top10 = final_list[:TOP_N]

    print("\n===== 今年以來跌幅最大（排除本業明顯惡化）前 10 檔 =====")
    print(f"{'代號':<6}{'名稱':<10}{'今年高點':>10}{'現價':>10}{'跌幅%':>8}{'營收年增%':>10}")
    for c in top10:
        yoy_str = f"{c['revenue_yoy_pct']:.1f}" if c["revenue_yoy_pct"] is not None else "N/A"
        print(f"{c['code']:<6}{c['name']:<10}{c['year_high']:>10.2f}{c['latest_close']:>10.2f}{c['drawdown_pct']:>8.1f}{yoy_str:>10}")

    with open("tw_oversold_result.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["代號", "名稱", "今年高點", "現價", "跌幅%", "營收年增%"])
        for c in top10:
            writer.writerow([
                c["code"], c["name"], c["year_high"], c["latest_close"],
                round(c["drawdown_pct"], 2),
                round(c["revenue_yoy_pct"], 2) if c["revenue_yoy_pct"] is not None else ""
            ])
    print("\n已輸出 tw_oversold_result.csv")


if __name__ == "__main__":
    main()