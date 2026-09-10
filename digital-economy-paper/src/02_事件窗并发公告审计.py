from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "outputs" / "ssci_empirical_completion_20260816"
FINAL = ROOT / "outputs" / "韩国数字化战略论文_正式版_20260816"
DATA_OUT = FINAL / "01_核心数据"
RESULT_OUT = FINAL / "02_模型与结果"
CACHE = ROOT / "work" / "formal_final_20260816" / "concurrent_disclosure_html_cache"
EVENT_PATH = SOURCE / "15_latest_text_aligned_event_study.csv"
PANEL_PATH = SOURCE / "03_frozen_augmented_research_panel.csv"
MARKET_CACHE = ROOT / "outputs" / "korea_digital_strategy_output" / "_cache" / "fiscal_market"

THREAD_LOCAL = threading.local()
REQUEST_LOCK = threading.Lock()
LAST_REQUEST_AT = 0.0
MIN_REQUEST_INTERVAL = 0.10


def http_session() -> requests.Session:
    current = getattr(THREAD_LOCAL, "session", None)
    if current is None:
        current = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        current.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8))
        current.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KoreaDigitalStrategyResearch/1.0",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
            }
        )
        THREAD_LOCAL.session = current
    return current


def throttled_get(url: str, params: dict[str, Any]) -> requests.Response:
    global LAST_REQUEST_AT
    error: Exception | None = None
    for attempt in range(6):
        try:
            with REQUEST_LOCK:
                delay = MIN_REQUEST_INTERVAL - (time.monotonic() - LAST_REQUEST_AT)
                if delay > 0:
                    time.sleep(delay)
                LAST_REQUEST_AT = time.monotonic()
            response = http_session().get(url, params=params, timeout=30)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            error = exc
            THREAD_LOCAL.session = None
            time.sleep(min(20.0, 1.0 * (2**attempt)))
    raise RuntimeError(f"DART HTML request failed after retries: {error}")


def trading_calendar() -> list[pd.Timestamp]:
    dates: set[pd.Timestamp] = set()
    for source in sorted(MARKET_CACHE.glob("*_raw.csv"))[:30]:
        frame = pd.read_csv(source, usecols=["date"])
        dates.update(pd.to_datetime(frame["date"], errors="coerce").dropna().tolist())
    return sorted(d for d in dates if pd.Timestamp("2015-01-01") <= d <= pd.Timestamp("2026-12-31"))


def event_windows(events: pd.DataFrame, calendar: list[pd.Timestamp]) -> pd.DataFrame:
    lookup = {date: index for index, date in enumerate(calendar)}
    rows: list[dict[str, Any]] = []
    for row in events.itertuples(index=False):
        start = pd.Timestamp(row.text_aligned_trading_date).normalize()
        index = lookup.get(start)
        if index is None or index + 2 >= len(calendar):
            end = (start + pd.offsets.BDay(2)).normalize()
            source = "business_day_fallback"
        else:
            end = calendar[index + 2]
            source = "observed_trading_calendar"
        rows.append(
            {
                "corp_code": str(row.corp_code).zfill(8),
                "year": int(row.year),
                "rcept_no": str(row.rcept_no),
                "event_start": start,
                "event_end": pd.Timestamp(end).normalize(),
                "calendar_source": source,
            }
        )
    return pd.DataFrame(rows)


def parse_page(html: str, query_date: pd.Timestamp, market: str) -> tuple[list[dict[str, Any]], int]:
    soup = BeautifulSoup(html, "lxml")
    total_node = soup.select_one("input#totalCnt")
    total = int(total_node.get("value", "0") or 0) if total_node else 0
    rows: list[dict[str, Any]] = []
    for tr in soup.select("table tbody tr"):
        report_link = tr.select_one("a[href*='rcpNo=']")
        corp_link = tr.select_one("a[href*='selectPopup.ax']")
        cells = tr.find_all("td")
        if report_link is None or corp_link is None or len(cells) < 5:
            continue
        report_match = re.search(r"rcpNo=(\d+)", report_link.get("href", ""))
        corp_match = re.search(r"openCorpInfoNew\('([0-9]{8})'", corp_link.get("href", ""))
        if not report_match or not corp_match:
            continue
        date_text = cells[4].get_text(" ", strip=True)
        rows.append(
            {
                "corp_code": corp_match.group(1),
                "corp_name": corp_link.get_text(" ", strip=True),
                "rcept_no": report_match.group(1),
                "report_nm": report_link.get_text(" ", strip=True),
                "flr_nm": cells[3].get_text(" ", strip=True),
                "rcept_dt": pd.to_datetime(date_text, format="%Y.%m.%d", errors="coerce").strftime("%Y%m%d"),
                "corp_cls": market,
                "query_date": query_date.strftime("%Y%m%d"),
            }
        )
    return rows, total


def fetch_market_day(query_date: pd.Timestamp, market: str) -> dict[str, Any]:
    CACHE.mkdir(parents=True, exist_ok=True)
    date_key = query_date.strftime("%Y%m%d")
    cached = CACHE / f"{date_key}_{market}.json.gz"
    if cached.exists():
        with gzip.open(cached, "rt", encoding="utf-8") as handle:
            return json.load(handle)

    url = f"https://dart.fss.or.kr/dsac001/main{market}.do"
    base_params = {
        "mdayCnt": "0",
        "selectDate": query_date.strftime("%Y.%m.%d"),
        "maxResults": "100",
    }
    first = throttled_get(url, {**base_params, "currentPage": "1"})
    rows, total = parse_page(first.text, query_date, market)
    pages = max(1, (total + 99) // 100)
    for page in range(2, pages + 1):
        response = throttled_get(url, {**base_params, "currentPage": str(page)})
        page_rows, _ = parse_page(response.text, query_date, market)
        rows.extend(page_rows)

    result = {
        "query_date": date_key,
        "market": market,
        "total": total,
        "pages": pages,
        "rows": rows,
        "source_url": url,
    }
    temp = cached.with_suffix(".tmp")
    with gzip.open(temp, "wt", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False)
    temp.replace(cached)
    return result


def classify(report_name: str) -> str:
    text = str(report_name)
    patterns = [
        ("target_annual_report", r"사업보고서"),
        ("earnings_or_forecast", r"영업\(?잠정\)?실적|매출액|손익구조|이익구조|결산실적|실적전망|공정공시.*실적|매출.*변경"),
        ("financing_or_security", r"유상증자|무상증자|전환사채|신주인수권|교환사채|주요사항보고서.*증권|감자결정"),
        ("governance_or_control", r"최대주주|대표이사|주주총회|자기주식|합병|분할|영업양수|영업양도|주식교환|임원.*주식"),
        ("audit_or_accounting", r"감사보고서|감사결과|감사의견|재무제표|회계감사|내부회계"),
        ("legal_or_regulatory", r"소송|가처분|배임|거래정지|상장폐지|관리종목|불성실공시|제재|회생절차"),
        ("other_periodic_report", r"분기보고서|반기보고서"),
        ("fair_disclosure_or_other", r"공정공시|수시공시|기타경영사항|자산양수|단일판매|공급계약|시설투자|타법인주식"),
    ]
    for category, pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return category
    return "other_disclosure"


def build_query_specs(windows: pd.DataFrame) -> list[tuple[pd.Timestamp, str]]:
    dates: set[pd.Timestamp] = set()
    for row in windows.itertuples(index=False):
        dates.update(pd.date_range(row.event_start, row.event_end, freq="D").tolist())
    return [(date, market) for date in sorted(dates) for market in ("Y", "K")]


def collect_sample_filings(results: list[dict[str, Any]], sample_codes: set[str]) -> pd.DataFrame:
    rows = [row for result in results for row in result.get("rows", []) if row["corp_code"] in sample_codes]
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).drop_duplicates(subset=["corp_code", "rcept_no"])
    frame["rcept_dt"] = pd.to_datetime(frame["rcept_dt"], format="%Y%m%d", errors="coerce")
    frame["concurrent_category"] = frame["report_nm"].map(classify)
    return frame.sort_values(["corp_code", "rcept_dt", "rcept_no"])


def attach_contamination(windows: pd.DataFrame, filings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    event_frame = windows.rename(columns={"rcept_no": "target_annual_report_rcept_no"})
    if filings.empty:
        summary = event_frame.rename(columns={"target_annual_report_rcept_no": "rcept_no"})
        for column in ["concurrent_filing_count", "high_relevance_count", "same_day_count"]:
            summary[column] = 0
        summary["has_concurrent_filing"] = False
        summary["has_high_relevance_concurrent"] = False
        summary["has_same_day_concurrent"] = False
        summary["concurrent_categories"] = ""
        summary["concurrent_report_names"] = ""
        return summary, pd.DataFrame()

    filing_frame = filings.rename(columns={"rcept_no": "concurrent_rcept_no"})
    merged = event_frame.merge(filing_frame, on="corp_code", how="left")
    merged = merged.loc[merged["rcept_dt"].between(merged["event_start"], merged["event_end"], inclusive="both")].copy()
    # Exclude only the focal filing. Corrections or other annual filings remain visible in the audit.
    concurrent = merged.loc[merged["concurrent_rcept_no"].ne(merged["target_annual_report_rcept_no"])].copy()
    high_categories = {
        "earnings_or_forecast",
        "financing_or_security",
        "governance_or_control",
        "audit_or_accounting",
        "legal_or_regulatory",
        "fair_disclosure_or_other",
    }
    concurrent["high_relevance"] = concurrent["concurrent_category"].isin(high_categories)
    concurrent["same_day"] = concurrent["rcept_dt"].eq(concurrent["event_start"])

    keys = ["corp_code", "year", "target_annual_report_rcept_no", "event_start", "event_end", "calendar_source"]
    grouped = concurrent.groupby(keys, dropna=False).agg(
        concurrent_filing_count=("concurrent_rcept_no", "nunique"),
        high_relevance_count=("high_relevance", "sum"),
        same_day_count=("same_day", "sum"),
        concurrent_categories=("concurrent_category", lambda x: "; ".join(sorted(set(map(str, x))))),
        concurrent_report_names=("report_nm", lambda x: " | ".join(list(dict.fromkeys(map(str, x)))[:12])),
    ).reset_index()
    summary = event_frame.merge(grouped, on=keys, how="left", validate="one_to_one")
    for column in ["concurrent_filing_count", "high_relevance_count", "same_day_count"]:
        summary[column] = summary[column].fillna(0).astype(int)
    summary["has_concurrent_filing"] = summary["concurrent_filing_count"].gt(0)
    summary["has_high_relevance_concurrent"] = summary["high_relevance_count"].gt(0)
    summary["has_same_day_concurrent"] = summary["same_day_count"].gt(0)
    summary["concurrent_categories"] = summary["concurrent_categories"].fillna("")
    summary["concurrent_report_names"] = summary["concurrent_report_names"].fillna("")
    summary = summary.rename(columns={"target_annual_report_rcept_no": "rcept_no"})
    return summary, concurrent


def run_clean_models(audit: pd.DataFrame) -> pd.DataFrame:
    optimizer_path = ROOT / "work" / "ssci_empirical_completion" / "08_optimize_models.py"
    spec = importlib.util.spec_from_file_location("optimizer", optimizer_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    panel = module.add_derived_variables().merge(
        audit[
            [
                "corp_code",
                "year",
                "has_concurrent_filing",
                "has_high_relevance_concurrent",
                "has_same_day_concurrent",
                "audit_coverage_verified",
                "concurrent_filing_count",
                "high_relevance_count",
            ]
        ],
        on=["corp_code", "year"],
        how="left",
        validate="one_to_one",
    )
    for column in ["has_concurrent_filing", "has_high_relevance_concurrent", "has_same_day_concurrent", "audit_coverage_verified"]:
        panel[column] = panel[column].fillna(False).astype(bool)

    specifications = [
        ("CONCURRENT_FULL", panel, "完整严格对齐事件样本"),
        ("CONCURRENT_VERIFIED_FULL", panel.loc[panel["audit_coverage_verified"]], "仅保留目标年报收件号已在DART历史页核验的事件"),
        ("CONCURRENT_CLEAN_ANY", panel.loc[panel["audit_coverage_verified"] & ~panel["has_concurrent_filing"]], "覆盖已核验且剔除事件窗内任何其他DART公告"),
        ("CONCURRENT_CLEAN_HIGH", panel.loc[panel["audit_coverage_verified"] & ~panel["has_high_relevance_concurrent"]], "覆盖已核验且剔除事件窗内高相关公告"),
        ("CONCURRENT_CLEAN_SAMEDAY", panel.loc[panel["audit_coverage_verified"] & ~panel["has_same_day_concurrent"]], "覆盖已核验且剔除事件日同日公告"),
    ]
    results: list[dict[str, Any]] = []
    for model_id, sample, note in specifications:
        for outcome in ["AlignedCAR_0_p2_w", "AlignedMarketAdjustedCAR_0_p2_w"]:
            rows, _, _ = module.fit_panel(
                sample,
                f"{model_id}_{outcome}",
                "concurrent_disclosure_audit",
                "robustness",
                note,
                outcome,
                ["Digital_z"],
                [*module.CORE_CONTROLS, *module.MARKET_CONTROLS],
                effect_spec="firm_event_date",
                covariance="firm_event_date",
                event_date="text_aligned_trading_date",
                sample_note=note,
            )
            results.extend(rows)
    frame = pd.DataFrame(results)
    ok = frame["status"].eq("ok")
    frame.loc[ok, "fdr_concurrent_family"] = module.bh_adjust(frame.loc[ok, "p_value"])
    return frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    DATA_OUT.mkdir(parents=True, exist_ok=True)
    RESULT_OUT.mkdir(parents=True, exist_ok=True)
    events = pd.read_csv(EVENT_PATH, dtype={"corp_code": str, "rcept_no": str})
    events["corp_code"] = events["corp_code"].str.zfill(8)
    events["text_aligned_trading_date"] = pd.to_datetime(events["text_aligned_trading_date"], errors="coerce")
    events = events.dropna(subset=["text_aligned_trading_date"]).copy()
    panel_flags = pd.read_csv(
        PANEL_PATH,
        usecols=["corp_code", "year", "corp_cls", "corp_name", "stock_code", "market", "historical_delisted_sample"],
        dtype={"corp_code": str, "stock_code": str},
    )
    panel_flags["corp_code"] = panel_flags["corp_code"].str.zfill(8)
    windows = event_windows(events, trading_calendar())
    query_specs = build_query_specs(windows)
    if args.limit:
        query_specs = query_specs[: args.limit]
    cached_count = sum((CACHE / f"{date.strftime('%Y%m%d')}_{market}.json.gz").exists() for date, market in query_specs)
    print(f"DART HTML market-day queries: {len(query_specs):,}; cached: {cached_count:,}", flush=True)

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_market_day, date, market): (date, market) for date, market in query_specs}
        for index, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if index % 100 == 0 or index == len(futures):
                print(f"Completed {index:,}/{len(futures):,}", flush=True)

    filings = collect_sample_filings(results, set(windows["corp_code"]))
    audit, matched = attach_contamination(windows, filings)
    audit = audit.merge(
        panel_flags.drop_duplicates(["corp_code", "year"]),
        on=["corp_code", "year"],
        how="left",
        validate="one_to_one",
    )
    observed_receipts = set(filings["rcept_no"].astype(str)) if not filings.empty else set()
    covered_target = audit["rcept_no"].astype(str).isin(observed_receipts)
    audit["audit_coverage_verified"] = covered_target
    audit.to_csv(DATA_OUT / "03_事件窗并发公告审计_公司年度.csv", index=False, encoding="utf-8-sig")
    matched.to_csv(DATA_OUT / "04_事件窗并发公告明细.csv", index=False, encoding="utf-8-sig")

    model_results = run_clean_models(audit)
    model_results.to_csv(RESULT_OUT / "03_剔除并发公告后的CAR模型.csv", index=False, encoding="utf-8-sig")
    matched_unique = int(matched["concurrent_rcept_no"].nunique()) if not matched.empty else 0
    summary = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "event_rows": int(len(audit)),
        "events_with_any_concurrent": int(audit["has_concurrent_filing"].sum()),
        "share_with_any_concurrent": float(audit["has_concurrent_filing"].mean()),
        "events_with_high_relevance": int(audit["has_high_relevance_concurrent"].sum()),
        "share_with_high_relevance": float(audit["has_high_relevance_concurrent"].mean()),
        "events_with_same_day": int(audit["has_same_day_concurrent"].sum()),
        "share_with_same_day": float(audit["has_same_day_concurrent"].mean()),
        "sample_company_filings_scanned": int(filings["rcept_no"].nunique()) if not filings.empty else 0,
        "matched_unique_filings": matched_unique,
        "focal_annual_report_receipts_observed": int(covered_target.sum()),
        "focal_annual_report_receipt_coverage": float(covered_target.mean()),
        "query_count": len(query_specs),
        "cached_query_count": len(query_specs),
        "source": "DART public daily disclosure pages mainY.do and mainK.do",
        "audit_scope": "All KOSPI/KOSDAQ filings from event trading day through trading day +2; filtered by stable DART corp_code",
        "classification_note": "The focal annual-report receipt number is excluded; all other filings, including annual-report corrections, remain auditable.",
    }
    (RESULT_OUT / "04_并发公告审计摘要.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
