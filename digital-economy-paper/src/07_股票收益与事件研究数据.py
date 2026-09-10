"""Collect fiscal-year-aligned Korean stock prices for the SSCI panel.

The script reads the final Korean v2 text panel, obtains adjusted and
unadjusted Korean equity prices through Daum Finance, and aligns each observation to the last
trading day on or before the firm's actual fiscal year end.  Market value is
calculated later after OpenDART historical issued-share counts are merged.
"""

from __future__ import annotations

import argparse
import calendar
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "korea_digital_strategy_output"
TEXT_PANEL = DATA_DIR / "04_digital_strategy_panel_korean_v2.xlsx"
OUTPUT_PATH = SCRIPT_DIR / "15_fiscal_year_market_prices.xlsx"
FINANCIAL_PATH = SCRIPT_DIR / "16_opendart_financial_controls.xlsx"
CACHE_DIR = DATA_DIR / "_cache" / "fiscal_market"


def normalize_ticker(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(6) if digits else ""


def fiscal_end_date(year: int, month: int) -> pd.Timestamp:
    month = min(max(int(month), 1), 12)
    return pd.Timestamp(year, month, calendar.monthrange(year, month)[1])


def normalize_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    result = data.copy()
    aliases = {
        "시가": "open",
        "고가": "high",
        "저가": "low",
        "종가": "close",
        "거래량": "volume",
        "등락률": "return_percent",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    result = result.rename(columns={key: value for key, value in aliases.items() if key in result.columns})
    result.index = pd.to_datetime(result.index, errors="coerce")
    result = result[result.index.notna()].sort_index()
    for column in result.columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def read_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    data = pd.read_csv(path, index_col=0)
    data.index = pd.to_datetime(data.index, errors="coerce")
    return data[data.index.notna()].sort_index()


def fetch_ticker(
    ticker: str,
    start: str,
    end: str,
    refresh: bool,
    sleep_seconds: float,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = CACHE_DIR / f"{ticker}_raw.csv"
    adjusted_path = CACHE_DIR / f"{ticker}_adjusted.csv"
    if not refresh and raw_path.exists() and adjusted_path.exists():
        return read_cache(raw_path), read_cache(adjusted_path), "validated_cache"
    raw = fetch_daum_prices(ticker, adjusted=False)
    time.sleep(max(sleep_seconds, 0.0))
    adjusted = fetch_daum_prices(ticker, adjusted=True)
    source = "daum_unadjusted_and_adjusted_prices"
    if raw.empty and adjusted.empty:
        raise RuntimeError("Daum Finance returned no price observations")
    raw.to_csv(raw_path, encoding="utf-8-sig")
    adjusted.to_csv(adjusted_path, encoding="utf-8-sig")
    return raw, adjusted, source


def fetch_daum_prices(ticker: str, adjusted: bool) -> pd.DataFrame:
    """Download raw or adjusted daily prices from Daum Finance."""
    session = requests.Session()
    referer = f"https://finance.daum.net/quotes/A{ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
    }
    session.get(referer, headers=headers, timeout=30).raise_for_status()
    response = session.get(
        f"https://finance.daum.net/api/charts/A{ticker}/days",
        params={"limit": 5000, "adjusted": str(bool(adjusted)).lower()},
        headers=headers,
        timeout=90,
    )
    response.raise_for_status()
    rows = response.json().get("data") or []
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).rename(
        columns={
            "openingPrice": "open",
            "highPrice": "high",
            "lowPrice": "low",
            "tradePrice": "close",
            "candleAccTradeVolume": "volume",
        }
    )
    frame.index = pd.to_datetime(frame["date"], errors="coerce")
    keep = [column for column in ("open", "high", "low", "close", "volume") if column in frame]
    return normalize_ohlcv(frame[keep])


def observation_on_or_before(
    data: pd.DataFrame, target: pd.Timestamp, max_days: int = 20
) -> tuple[pd.Timestamp | None, pd.Series | None]:
    if data.empty:
        return None, None
    candidates = data.loc[(data.index <= target) & (data.index >= target - pd.Timedelta(days=max_days))]
    candidates = candidates[candidates.get("close", pd.Series(index=candidates.index, dtype=float)).notna()]
    if candidates.empty:
        return None, None
    date = candidates.index[-1]
    return date, candidates.iloc[-1]


def calculate_firm_year(
    row: pd.Series,
    raw: pd.DataFrame,
    adjusted: pd.DataFrame,
    source: str,
) -> dict[str, Any]:
    year = int(row["year"])
    month = int(row.get("acc_mt") or 12)
    reported_end = pd.to_datetime(row.get("share_count_date"), errors="coerce")
    reported_prior = pd.to_datetime(row.get("prior_share_count_date"), errors="coerce")
    target_end = reported_end if pd.notna(reported_end) and int(reported_end.year) == year else fiscal_end_date(year, month)
    target_prior = reported_prior if pd.notna(reported_prior) and int(reported_prior.year) == year - 1 else fiscal_end_date(year - 1, month)
    fiscal_date_source = "opendart_share_count_date" if pd.notna(reported_end) and int(reported_end.year) == year else "dart_current_account_month"
    raw_date, raw_obs = observation_on_or_before(raw, target_end)
    adj_date, adj_obs = observation_on_or_before(adjusted, target_end)
    prior_date, prior_obs = observation_on_or_before(adjusted, target_prior)
    end_price = float(raw_obs["close"]) if raw_obs is not None else None
    adjusted_end = float(adj_obs["close"]) if adj_obs is not None else None
    adjusted_prior = float(prior_obs["close"]) if prior_obs is not None else None
    annual_return = (
        adjusted_end / adjusted_prior - 1
        if adjusted_end is not None and adjusted_prior not in (None, 0)
        else None
    )
    window = adjusted.loc[
        (adjusted.index > (prior_date if prior_date is not None else target_prior))
        & (adjusted.index <= (adj_date if adj_date is not None else target_end))
    ].copy()
    daily_returns = window["close"].pct_change().dropna() if "close" in window else pd.Series(dtype=float)
    return {
        "corp_code": str(row["corp_code"]).zfill(8),
        "corp_name": row.get("corp_name"),
        "stock_code": normalize_ticker(row.get("stock_code")),
        "year": year,
        "acc_mt": month,
        "fiscal_year_end_target": target_end.date().isoformat(),
        "fiscal_year_end_source": fiscal_date_source,
        "market_price_date": raw_date.date().isoformat() if raw_date is not None else None,
        "FiscalYearEndPrice": end_price,
        "adjusted_price_date": adj_date.date().isoformat() if adj_date is not None else None,
        "AdjustedFiscalYearEndPrice": adjusted_end,
        "prior_adjusted_price_date": prior_date.date().isoformat() if prior_date is not None else None,
        "PriorAdjustedFiscalYearEndPrice": adjusted_prior,
        "FiscalYearStockReturn": annual_return,
        "FiscalYearDailyVolatility": float(daily_returns.std()) if len(daily_returns) >= 20 else None,
        "FiscalYearTradingDays": int(len(window)),
        "market_price_status": "ok" if end_price is not None else "missing_fiscal_end_price",
        "market_price_source": source,
        "market_price_error": "",
    }


def write_output(panel: pd.DataFrame, audit: pd.DataFrame) -> None:
    coverage_rows = []
    for column in (
        "FiscalYearEndPrice",
        "FiscalYearStockReturn",
        "FiscalYearDailyVolatility",
    ):
        coverage_rows.append(
            {
                "variable": column,
                "nonmissing_n": int(panel[column].notna().sum()),
                "missing_n": int(panel[column].isna().sum()),
                "coverage_rate": float(panel[column].notna().mean()),
            }
        )
    summary = pd.DataFrame(
        [
            {"metric": "firm_year_rows", "value": len(panel)},
            {"metric": "unique_firms", "value": panel["corp_code"].nunique()},
            {"metric": "successful_price_rows", "value": int(panel["market_price_status"].eq("ok").sum())},
            {"metric": "failed_tickers", "value": int(audit["status"].ne("ok").sum())},
        ]
    )
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        panel.to_excel(writer, sheet_name="fiscal_market_panel", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)
        pd.DataFrame(coverage_rows).to_excel(writer, sheet_name="coverage", index=False)
        audit.to_excel(writer, sheet_name="ticker_download_audit", index=False)


def run(refresh: bool, sleep_seconds: float, limit: int | None) -> None:
    text = pd.read_excel(
        TEXT_PANEL,
        dtype={"corp_code": str, "stock_code": str, "rcept_no": str},
    )
    base = text[
        ["corp_code", "corp_name", "stock_code", "year", "acc_mt"]
    ].drop_duplicates(["corp_code", "year"]).copy()
    base["corp_code"] = base["corp_code"].astype(str).str.zfill(8)
    base["stock_code"] = base["stock_code"].map(normalize_ticker)
    if FINANCIAL_PATH.exists():
        financial_dates = pd.read_excel(
            FINANCIAL_PATH,
            sheet_name="financial_controls",
            dtype={"corp_code": str},
            usecols=lambda column: column in {"corp_code", "year", "share_count_date"},
        )
        financial_dates["corp_code"] = financial_dates["corp_code"].astype(str).str.zfill(8)
        financial_dates["year"] = pd.to_numeric(financial_dates["year"], errors="coerce").astype("Int64")
        financial_dates = financial_dates.drop_duplicates(["corp_code", "year"])
        base = base.merge(financial_dates, on=["corp_code", "year"], how="left", validate="one_to_one")
        base = base.sort_values(["corp_code", "year"])
        prior_date = base.groupby("corp_code")["share_count_date"].shift(1)
        consecutive = base["year"].sub(base.groupby("corp_code")["year"].shift(1)).eq(1)
        base["prior_share_count_date"] = prior_date.where(consecutive)
    tickers = sorted(base["stock_code"].dropna().unique())
    if limit is not None:
        tickers = tickers[:limit]
        base = base[base["stock_code"].isin(tickers)].copy()
    start = f"{int(base['year'].min()) - 1}0101"
    end = f"{int(base['year'].max())}1231"
    results: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    for sequence, ticker in enumerate(tickers, start=1):
        print(f"[{sequence:03d}/{len(tickers):03d}] Market {ticker}", flush=True)
        try:
            raw, adjusted, source = fetch_ticker(
                ticker, start, end, refresh, sleep_seconds
            )
            rows = base[base["stock_code"].eq(ticker)]
            for _, row in rows.iterrows():
                results.append(calculate_firm_year(row, raw, adjusted, source))
            audits.append(
                {
                    "stock_code": ticker,
                    "status": "ok",
                    "source": source,
                    "raw_rows": len(raw),
                    "adjusted_rows": len(adjusted),
                    "first_date": raw.index.min().date().isoformat() if len(raw) else None,
                    "last_date": raw.index.max().date().isoformat() if len(raw) else None,
                    "error": "",
                }
            )
        except Exception as exc:
            error = str(exc)
            console_error = error.encode("ascii", "backslashreplace").decode("ascii")
            print(f"  ERROR: {console_error[:500]}", flush=True)
            rows = base[base["stock_code"].eq(ticker)]
            for _, row in rows.iterrows():
                result = calculate_firm_year(row, pd.DataFrame(), pd.DataFrame(), "")
                result["market_price_status"] = "error"
                result["market_price_error"] = error
                results.append(result)
            audits.append({"stock_code": ticker, "status": "error", "error": error})
        if sequence % 10 == 0 or sequence == len(tickers):
            write_output(pd.DataFrame(results), pd.DataFrame(audits))
    market = pd.DataFrame(results).sort_values(["corp_code", "year"]).reset_index(drop=True)
    write_output(market, pd.DataFrame(audits))
    print(f"Wrote: {OUTPUT_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=0.20)
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.refresh, max(args.sleep_seconds, 0.0), args.limit)
