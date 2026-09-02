#!/usr/bin/env python3
"""
Barometr Ryzyka Finansowego
===========================
Zbiera sygnały z wielu źródeł i liczy prosty wynik 0-100.
Im wyższy wynik, tym większe napięcie w systemie finansowym.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    import yfinance as yf
except ImportError:
    yf = None

# ============================================================
# KONFIGURACJA
# ============================================================

DATA_DIR = Path("monitor_data")
DATA_DIR.mkdir(exist_ok=True)
REPORT_PATH = DATA_DIR / "latest_report.json"

FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()

# Serie FRED (darmowe)
FRED_SERIES = {
    "VIXCLS": "VIX (strach na giełdzie)",
    "T10Y2Y": "Krzywa 10y-2y (odwrócenie = ostrzeżenie)",
    "T10Y3M": "Krzywa 10y-3m",
    "BAMLH0A0HYM2": "Spready high-yield (kredyt śmieciowy)",
    "DFF": "Stopa Fed Funds",
    "DTWEXBGS": "Indeks dolara (DXY proxy)",
    "NFCI": "Chicago Fed National Financial Conditions",
    "STLFSI4": "St. Louis Fed Stress Index",
    "WALCL": "Bilans Fed (płynność)",
}

# Ticker yfinance
YF_TICKERS = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "Nasdaq",
    "^VIX": "VIX",
    "HYG": "ETF high-yield",
    "LQD": "ETF corporate IG",
    "TLT": "ETF długich obligacji",
    "GLD": "Złoto",
    "UUP": "Dolar ETF",
    "XLF": "Sektor finansowy",
}

NEWS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://www.federalreserve.gov/feeds/press_all.xml",
]

NEWS_KEYWORDS = [
    r"recession",
    r"financial crisis",
    r"bank (stress|failure|collapse)",
    r"credit crunch",
    r"default",
    r"bailout",
    r"yield curve",
    r"emergency (cut|rate|meeting)",
    r"liquidity crisis",
    r"market crash",
    r"systemic risk",
]

SEC_STRESS_KEYWORDS = [
    r"going concern",
    r"substantial doubt",
    r"impairment",
    r"goodwill impairment",
    r"restructuring",
    r"bankruptcy",
    r"covenant breach",
    r"material weakness",
    r"liquidity position",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("CrisisBarometer")


# ============================================================
# ŹRÓDŁA DANYCH
# ============================================================

def fred_latest(series_id: str) -> Optional[Tuple[str, float]]:
    """Zwraca (data, wartość) najnowszej obserwacji z FRED."""
    if not FRED_API_KEY:
        return None
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 5,
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        for o in obs:
            val = o.get("value")
            if val not in (None, "."):
                return o.get("date"), float(val)
    except Exception as e:
        log.warning("FRED %s: %s", series_id, e)
    return None


def fred_history(series_id: str, limit: int = 30) -> List[float]:
    if not FRED_API_KEY:
        return []
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        vals = []
        for o in r.json().get("observations", []):
            v = o.get("value")
            if v not in (None, "."):
                vals.append(float(v))
        return list(reversed(vals))
    except Exception as e:
        log.warning("FRED history %s: %s", series_id, e)
        return []


def fetch_fred_block() -> Dict[str, Any]:
    out = {}
    for sid, label in FRED_SERIES.items():
        latest = fred_latest(sid)
        hist = fred_history(sid, 20)
        item = {"id": sid, "label": label, "value": None, "date": None, "change_pct": None}
        if latest:
            item["date"], item["value"] = latest
            if len(hist) >= 2 and hist[-2] != 0:
                item["change_pct"] = round((hist[-1] - hist[-2]) / abs(hist[-2]) * 100, 2)
            item["history"] = hist[-10:]
        out[sid] = item
        time.sleep(0.25)
    return out


def fetch_markets() -> Dict[str, Any]:
    if yf is None:
        log.warning("yfinance niedostępne")
        return {}
    out = {}
    for ticker, label in YF_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1mo")
            if hist is None or len(hist) < 3:
                continue
            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            week_ago = float(hist["Close"].iloc[-6]) if len(hist) >= 6 else prev
            chg_1d = (last - prev) / prev * 100
            chg_5d = (last - week_ago) / week_ago * 100
            out[ticker] = {
                "label": label,
                "price": round(last, 2),
                "change_1d_pct": round(chg_1d, 2),
                "change_5d_pct": round(chg_5d, 2),
            }
        except Exception as e:
            log.warning("Yahoo %s: %s", ticker, e)
    return out


def fetch_news_stress() -> Dict[str, Any]:
    hits = []
    total_items = 0
    for feed in NEWS_FEEDS:
        try:
            r = requests.get(feed, timeout=15, headers={"User-Agent": "CrisisBarometer/1.0"})
            if r.status_code != 200:
                continue
            text = r.text
            # proste wyciągnięcie tytułów
            titles = re.findall(r"<title>(.*?)</title>", text, flags=re.I | re.S)
            for title in titles[1:15]:  # pomiń tytuł kanału
                title_clean = re.sub(r"<.*?>", "", title).strip()
                total_items += 1
                for kw in NEWS_KEYWORDS:
                    if re.search(kw, title_clean, re.I):
                        hits.append({"title": title_clean[:180], "keyword": kw, "source": feed})
                        break
        except Exception as e:
            log.warning("News feed %s: %s", feed, e)
        time.sleep(0.3)
    return {"hits": hits[:20], "scanned_titles": total_items, "hit_count": len(hits)}


def fetch_sec_stress_sample() -> Dict[str, Any]:
    """Lekki skan ostatnich 8-K z EDGAR recent (ograniczony)."""
    # Publiczny feed atom ostatnich filingów
    url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company=&dateb=&owner=include&count=40&output=atom"
    headers = {"User-Agent": "CrisisBarometer research@personal-use.com"}
    hits = []
    try:
        r = requests.get(url, headers=headers, timeout=25)
        if r.status_code != 200:
            return {"hits": [], "error": f"HTTP {r.status_code}"}
        entries = re.findall(r"<entry>(.*?)</entry>", r.text, flags=re.S | re.I)
        for ent in entries[:25]:
            title_m = re.search(r"<title[^>]*>(.*?)</title>", ent, re.S | re.I)
            summary_m = re.search(r"<summary[^>]*>(.*?)</summary>", ent, re.S | re.I)
            title = re.sub(r"<.*?>", "", title_m.group(1)).strip() if title_m else ""
            summary = re.sub(r"<.*?>", "", summary_m.group(1)).strip() if summary_m else ""
            blob = f"{title} {summary}".lower()
            matched = [kw for kw in SEC_STRESS_KEYWORDS if re.search(kw, blob, re.I)]
            if matched:
                hits.append({"title": title[:160], "keywords": matched[:3]})
    except Exception as e:
        log.warning("SEC scan: %s", e)
        return {"hits": [], "error": str(e)}
    return {"hits": hits[:15], "hit_count": len(hits)}


# ============================================================
# SCORING 0-100
# ============================================================

def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def score_vix(v: Optional[float]) -> Tuple[float, str]:
    if v is None:
        return 0.0, "Brak VIX"
    if v < 15:
        return 5, f"VIX {v:.1f} – spokój"
    if v < 20:
        return 20, f"VIX {v:.1f} – normalnie"
    if v < 25:
        return 40, f"VIX {v:.1f} – podwyższony niepokój"
    if v < 30:
        return 60, f"VIX {v:.1f} – wysoki stres"
    if v < 40:
        return 80, f"VIX {v:.1f} – bardzo wysoki stres"
    return 95, f"VIX {v:.1f} – ekstremalny strach"


def score_yield_curve(t10y2y: Optional[float]) -> Tuple[float, str]:
    if t10y2y is None:
        return 0.0, "Brak krzywej 10y-2y"
    # Ujemna = odwrócona = klasyczny sygnał recesyjny
    if t10y2y >= 0.5:
        return 10, f"Krzywa +{t10y2y:.2f} – normalna"
    if t10y2y >= 0:
        return 25, f"Krzywa +{t10y2y:.2f} – płaska"
    if t10y2y >= -0.5:
        return 55, f"Krzywa {t10y2y:.2f} – odwrócona"
    return 75, f"Krzywa {t10y2y:.2f} – mocno odwrócona"


def score_hy_spread(spread: Optional[float]) -> Tuple[float, str]:
    # BAMLH0A0HYM2 w punktach procentowych
    if spread is None:
        return 0.0, "Brak spreadów HY"
    if spread < 3.5:
        return 15, f"HY spread {spread:.2f}% – spokojny kredyt"
    if spread < 5:
        return 35, f"HY spread {spread:.2f}% – lekko podwyższony"
    if spread < 7:
        return 55, f"HY spread {spread:.2f}% – napięcie kredytowe"
    if spread < 10:
        return 75, f"HY spread {spread:.2f}% – silny stres kredytu"
    return 90, f"HY spread {spread:.2f}% – kryzysowy poziom kredytu"


def score_nfci(nfci: Optional[float]) -> Tuple[float, str]:
    # NFCI: 0 = średnia, dodatnie = ciaśniejsze warunki
    if nfci is None:
        return 0.0, "Brak NFCI"
    if nfci < -0.3:
        return 10, f"NFCI {nfci:.2f} – luźne warunki"
    if nfci < 0:
        return 25, f"NFCI {nfci:.2f} – neutralne"
    if nfci < 0.5:
        return 50, f"NFCI {nfci:.2f} – zacieśnienie"
    if nfci < 1.0:
        return 70, f"NFCI {nfci:.2f} – silne zacieśnienie"
    return 90, f"NFCI {nfci:.2f} – warunki kryzysowe"


def score_markets(markets: Dict[str, Any]) -> Tuple[float, List[str]]:
    notes = []
    score = 0.0
    sp = markets.get("^GSPC")
    if sp:
        d = sp.get("change_1d_pct") or 0
        w = sp.get("change_5d_pct") or 0
        if d <= -2:
            score += 15
            notes.append(f"S&P 500 spadł o {d:.1f}% dziennie")
        elif d <= -1:
            score += 8
            notes.append(f"S&P 500 {d:.1f}% dziennie")
        if w <= -5:
            score += 20
            notes.append(f"S&P 500 {w:.1f}% w 5 dni")
        elif w <= -3:
            score += 10
            notes.append(f"S&P 500 {w:.1f}% w 5 dni")
    xlf = markets.get("XLF")
    if xlf and (xlf.get("change_5d_pct") or 0) <= -4:
        score += 12
        notes.append(f"Sektor finansowy słaby ({xlf['change_5d_pct']:.1f}% / 5d)")
    hyg = markets.get("HYG")
    lqd = markets.get("LQD")
    if hyg and lqd:
        # jeśli HY spada mocniej niż IG – stres kredytu
        if (hyg.get("change_5d_pct") or 0) < (lqd.get("change_5d_pct") or 0) - 1.5:
            score += 10
            notes.append("High-yield słabszy od kredytu inwestycyjnego")
    return clamp(score, 0, 40), notes


def score_news(news: Dict[str, Any]) -> Tuple[float, List[str]]:
    n = news.get("hit_count") or 0
    notes = []
    if n == 0:
        return 0, ["Brak alarmujących nagłówków"]
    if n <= 2:
        s = 15
    elif n <= 5:
        s = 30
    else:
        s = 45
    notes.append(f"Trafienia w newsach o stresie: {n}")
    for h in (news.get("hits") or [])[:3]:
        notes.append(f"News: {h.get('title', '')[:80]}")
    return float(s), notes


def score_sec(sec: Dict[str, Any]) -> Tuple[float, List[str]]:
    n = sec.get("hit_count") or len(sec.get("hits") or [])
    notes = []
    if n == 0:
        return 0, ["Brak stresujących 8-K w próbce"]
    s = min(35, 8 * n)
    notes.append(f"SEC 8-K ze słowami stresu: {n}")
    for h in (sec.get("hits") or [])[:3]:
        notes.append(f"8-K: {h.get('title', '')[:80]}")
    return float(s), notes


def compute_barometer(fred: Dict, markets: Dict, news: Dict, sec: Dict) -> Dict[str, Any]:
    components = []
    reasons: List[str] = []

    vix_val = None
    if fred.get("VIXCLS", {}).get("value") is not None:
        vix_val = fred["VIXCLS"]["value"]
    elif markets.get("^VIX", {}).get("price") is not None:
        vix_val = markets["^VIX"]["price"]
    s, note = score_vix(vix_val)
    components.append(("VIX / strach", s, 0.20))
    reasons.append(note)

    s, note = score_yield_curve(fred.get("T10Y2Y", {}).get("value"))
    components.append(("Krzywa rentowności", s, 0.18))
    reasons.append(note)

    s, note = score_hy_spread(fred.get("BAMLH0A0HYM2", {}).get("value"))
    components.append(("Spready kredytowe HY", s, 0.18))
    reasons.append(note)

    s, note = score_nfci(fred.get("NFCI", {}).get("value"))
    components.append(("Warunki finansowe (NFCI)", s, 0.14))
    reasons.append(note)

    s, notes = score_markets(markets)
    components.append(("Rynki akcji / sektory", s, 0.15))
    reasons.extend(notes)

    s, notes = score_news(news)
    components.append(("Newsy / nagłówki", s, 0.08))
    reasons.extend(notes)

    s, notes = score_sec(sec)
    components.append(("Sygnały SEC (8-K)", s, 0.07))
    reasons.extend(notes)

    # ważona średnia
    total_w = sum(w for _, _, w in components) or 1
    score = sum(val * w for _, val, w in components) / total_w
    score = round(clamp(score), 1)

    if score < 25:
        level = "spokojnie"
        level_pl = "🟢 Spokojnie"
        desc = "Warunki finansowe wyglądają stabilnie. Brak silnych sygnałów ostrzegawczych."
    elif score < 45:
        level = "uwaga"
        level_pl = "🟡 Podwyższona uwaga"
        desc = "Widać pierwsze oznaki napięcia. Warto obserwować kolejne odczyty."
    elif score < 70:
        level = "wysoki"
        level_pl = "🟠 Wysoki poziom ryzyka"
        desc = "Kilka wskaźników wskazuje na rosnący stres. Zachowaj ostrożność."
    else:
        level = "krytyczny"
        level_pl = "🔴 Bardzo wysoki stres"
        desc = "Silne sygnały napięcia w systemie. To nie prognoza daty kryzysu, ale warunki są trudne."

    return {
        "score": score,
        "level": level,
        "level_label": level_pl,
        "description": desc,
        "components": [
            {"name": n, "score": round(v, 1), "weight": w} for n, v, w in components
        ],
        "reasons": reasons[:12],
    }


# ============================================================
# MAIN
# ============================================================

def run() -> Dict[str, Any]:
    log.info("Start Barometru Ryzyka Finansowego")
    if not FRED_API_KEY:
        log.warning("Brak FRED_API_KEY – część makro będzie pusta")

    fred = fetch_fred_block()
    log.info("FRED: %s serii", len([k for k, v in fred.items() if v.get("value") is not None]))

    markets = fetch_markets()
    log.info("Rynki: %s tickerów", len(markets))

    news = fetch_news_stress()
    log.info("Newsy: %s trafień", news.get("hit_count"))

    sec = fetch_sec_stress_sample()
    log.info("SEC: %s trafień", sec.get("hit_count") or len(sec.get("hits") or []))

    barometer = compute_barometer(fred, markets, news, sec)

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "barometer": barometer,
        "fred": fred,
        "markets": markets,
        "news": news,
        "sec": sec,
        "meta": {
            "fred_key_present": bool(FRED_API_KEY),
            "version": "1.0",
        },
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Zapisano %s | SCORE=%s (%s)", REPORT_PATH, barometer["score"], barometer["level_label"])
    return report


if __name__ == "__main__":
    run()
