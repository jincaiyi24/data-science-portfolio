"""
SSCI financial controls pipeline for the Korean digital strategy project.

This script builds firm-year financial controls from English OpenDART
financial statement APIs and prepares merge-ready regression datasets.

It is intentionally separate from korea_digital_strategy_pipeline.py so the
long annual-report text scoring job can keep running without interruption.

Default inputs
--------------
outputs/korea_digital_strategy_output/
    03_selected_research_sample.xlsx
    04_digital_strategy_panel.xlsx  (optional; used for final merge if present)

Default outputs
---------------
outputs/korea_digital_strategy_output/
    06_financial_controls_panel.xlsx
    06_financial_statement_raw_long.xlsx
    07_market_value_panel_template.xlsx
    08_final_regression_dataset_pre_market.xlsx

Run
---
python ssci_financial_controls_pipeline.py

Notes
-----
The OpenDART API key is read from DART_API_KEY. If missing, the script asks
for it without echoing it to the terminal.
"""

from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent

REQUIRED_PIP_PACKAGES = {
    "pandas": "pandas",
    "openpyxl": "openpyxl",
    "requests": "requests",
    "tqdm": "tqdm",
}


def ensure_runtime_packages() -> None:
    if os.environ.get("KOREA_PIPELINE_SKIP_AUTO_INSTALL") == "1":
        return
    missing = [
        pip_name
        for module_name, pip_name in REQUIRED_PIP_PACKAGES.items()
        if importlib.util.find_spec(module_name) is None
    ]
    if not missing:
        return

    print("Missing Python packages detected:")
    print("  " + " ".join(missing))
    print("Installing them with the current Python interpreter...")
    try:
        subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])
    except Exception:
        pass
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", *missing])
    except subprocess.CalledProcessError:
        print("Default pip source failed. Retrying with Tsinghua PyPI mirror...")
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "-i",
                "https://pypi.tuna.tsinghua.edu.cn/simple",
                *missing,
            ]
        )
    importlib.invalidate_caches()


ensure_runtime_packages()

import pandas as pd

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

try:
    from tqdm import tqdm as _tqdm  # type: ignore
except ImportError:  # pragma: no cover
    _tqdm = None


ENG_API_BASE = "https://engopendart.fss.or.kr/engapi"
ANNUAL_REPORT_CODE = "11011"


def progress(iterable: Iterable[Any], total: Optional[int] = None, desc: str = "") -> Iterable[Any]:
    if _tqdm is not None:
        return _tqdm(iterable, total=total, desc=desc)
    for idx, item in enumerate(iterable, start=1):
        if idx == 1 and desc:
            print(desc)
        if idx % 100 == 0:
            suffix = f"/{total}" if total else ""
            print(f"  {desc}: {idx}{suffix}")
        yield item


def write_excel(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    max_excel_rows = 1_048_576
    if len(df) <= max_excel_rows:
        df.to_excel(path, index=False)
        return
    rows_per_sheet = max_excel_rows - 1
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for idx, start in enumerate(range(0, len(df), rows_per_sheet), start=1):
            end = min(start + rows_per_sheet, len(df))
            df.iloc[start:end].to_excel(writer, index=False, sheet_name=f"part_{idx}")


def parse_number(value: Any) -> Optional[float]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text or text in {"-", "nan", "None"}:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    text = text.replace(",", "").replace(" ", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def safe_divide(numerator: Any, denominator: Any) -> Optional[float]:
    if numerator is None or denominator is None:
        return None
    try:
        numerator_f = float(numerator)
        denominator_f = float(denominator)
    except (TypeError, ValueError):
        return None
    if denominator_f == 0 or math.isnan(denominator_f):
        return None
    return numerator_f / denominator_f


def safe_log(value: Any) -> Optional[float]:
    try:
        value_f = float(value)
    except (TypeError, ValueError):
        return None
    if value_f <= 0 or math.isnan(value_f):
        return None
    return math.log(value_f)


class OpenDartError(RuntimeError):
    pass


class OpenDartClient:
    def __init__(self, api_key: Optional[str] = None, sleep_seconds: float = 0.12, retries: int = 3) -> None:
        self.api_key = (api_key or os.getenv("DART_API_KEY") or "").strip()
        self.sleep_seconds = sleep_seconds
        self.retries = retries
        self.session = requests.Session() if requests is not None else None

    def require_key(self) -> None:
        if self.api_key:
            return
        try:
            entered = getpass.getpass("Enter your OpenDART API key (DART_API_KEY): ").strip()
        except Exception:
            entered = input("Enter your OpenDART API key (DART_API_KEY): ").strip()
        if entered:
            self.api_key = entered
        if not self.api_key:
            raise OpenDartError("DART_API_KEY is required.")

    def get_json(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self.require_key()
        request_params = {k: v for k, v in params.items() if v is not None and v != ""}
        request_params["crtfc_key"] = self.api_key
        url = f"{ENG_API_BASE}/{endpoint}"
        last_error: Optional[BaseException] = None
        for attempt in range(1, self.retries + 1):
            try:
                if self.session is not None:
                    response = self.session.get(url, params=request_params, timeout=60)
                    response.raise_for_status()
                    data = response.json()
                else:
                    query = urllib.parse.urlencode(request_params)
                    with urllib.request.urlopen(f"{url}?{query}", timeout=60) as response:
                        data = json.loads(response.read().decode("utf-8"))
                if self.sleep_seconds:
                    time.sleep(self.sleep_seconds)
                return data
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(min(attempt * 2.0, 8.0))
        raise OpenDartError(f"OpenDART request failed after {self.retries} attempts: {last_error}")


@dataclass
class Config:
    out_dir: Path = SCRIPT_DIR / "korea_digital_strategy_output"
    start_year: int = 2015
    end_year: int = 2025
    sleep_seconds: float = 0.12
    retries: int = 3
    refresh_financials: bool = False
    save_raw_long: bool = True
    sample_limit: Optional[int] = None

    @property
    def cache_dir(self) -> Path:
        return self.out_dir / "_cache"


FINANCIAL_ITEM_SPECS: Dict[str, Dict[str, Any]] = {
    "TotalAssets": {
        "sj_div": ["BS"],
        "ids": ["ifrs-full_Assets"],
        "name_patterns": [r"^total assets$", r"^assets$"],
    },
    "TotalLiabilities": {
        "sj_div": ["BS"],
        "ids": ["ifrs-full_Liabilities"],
        "name_patterns": [r"^total liabilities$", r"^liabilities$"],
    },
    "TotalEquity": {
        "sj_div": ["BS"],
        "ids": ["ifrs-full_Equity"],
        "name_patterns": [r"^total equity$", r"^equity$"],
    },
    "EquityAttributableToOwners": {
        "sj_div": ["BS"],
        "ids": ["ifrs-full_EquityAttributableToOwnersOfParent"],
        "name_patterns": [r"equity attributable to owners", r"parent company owner"],
    },
    "CurrentAssets": {
        "sj_div": ["BS"],
        "ids": ["ifrs-full_CurrentAssets"],
        "name_patterns": [r"^current assets$"],
    },
    "CurrentLiabilities": {
        "sj_div": ["BS"],
        "ids": ["ifrs-full_CurrentLiabilities"],
        "name_patterns": [r"^current liabilities$"],
    },
    "Cash": {
        "sj_div": ["BS", "CF"],
        "ids": ["ifrs-full_CashAndCashEquivalents"],
        "name_patterns": [r"cash and cash equivalents"],
    },
    "PPE": {
        "sj_div": ["BS"],
        "ids": ["ifrs-full_PropertyPlantAndEquipment"],
        "name_patterns": [r"property,\s*plant and equipment", r"tangible assets"],
    },
    "Sales": {
        "sj_div": ["IS", "CIS"],
        "ids": [
            "ifrs-full_Revenue",
            "ifrs-full_RevenueFromContractsWithCustomers",
            "ifrs-full_SalesRevenueNet",
        ],
        "name_patterns": [r"^revenue$", r"^sales$", r"sales revenue", r"revenue from contracts"],
        "exclude_patterns": [r"cost", r"finance", r"interest"],
    },
    "OperatingIncome": {
        "sj_div": ["IS", "CIS"],
        "ids": ["dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"],
        "name_patterns": [r"operating income", r"operating profit", r"operating loss"],
    },
    "NetIncome": {
        "sj_div": ["IS", "CIS"],
        "ids": ["ifrs-full_ProfitLoss"],
        "name_patterns": [r"^profit \(loss\)$", r"^profit for the year$", r"^net income", r"^net profit"],
        "exclude_patterns": [r"comprehensive", r"before tax", r"attributable"],
    },
    "R&DExpense": {
        "sj_div": ["IS", "CIS"],
        "ids": ["dart_ResearchAndDevelopmentExpenses"],
        "name_patterns": [r"research and development", r"\br&d\b", r"development expense"],
    },
    "CAPEX": {
        "sj_div": ["CF"],
        "ids": [
            "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            "ifrs-full_PaymentsToAcquirePropertyPlantAndEquipment",
        ],
        "name_patterns": [
            r"purchase of property,\s*plant and equipment",
            r"payments to acquire property",
            r"acquisition of property",
            r"acquisitions of property",
        ],
        "use_absolute": True,
    },
}


def normalize_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def row_matches_spec(row: Dict[str, Any], spec: Dict[str, Any], by_id: bool) -> bool:
    sj_divs = spec.get("sj_div") or []
    if sj_divs and str(row.get("sj_div") or "") not in sj_divs:
        return False
    account_id = str(row.get("account_id") or "")
    account_name = normalize_name(row.get("account_nm"))

    if by_id and account_id in spec.get("ids", []):
        return True
    if by_id:
        return False

    for pattern in spec.get("exclude_patterns", []):
        if re.search(pattern, account_name, flags=re.IGNORECASE):
            return False
    return any(re.search(pattern, account_name, flags=re.IGNORECASE) for pattern in spec.get("name_patterns", []))


def choose_financial_value(rows: Sequence[Dict[str, Any]], spec: Dict[str, Any]) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    for by_id in (True, False):
        candidates = [row for row in rows if row_matches_spec(row, spec, by_id=by_id)]
        candidates = [row for row in candidates if parse_number(row.get("thstrm_amount")) is not None]
        if not candidates:
            continue
        candidates.sort(key=lambda row: int(re.sub(r"\D", "", str(row.get("ord") or "999999")) or "999999"))
        row = candidates[0]
        value = parse_number(row.get("thstrm_amount"))
        if value is not None and spec.get("use_absolute"):
            value = abs(value)
        return value, str(row.get("account_id") or ""), str(row.get("account_nm") or "")
    return None, None, None


def load_firm_year_tasks(config: Config) -> pd.DataFrame:
    text_panel_path = config.out_dir / "04_digital_strategy_panel.xlsx"
    selected_path = config.out_dir / "03_selected_research_sample.xlsx"

    if text_panel_path.exists():
        panel = pd.read_excel(text_panel_path, dtype={"corp_code": str, "stock_code": str})
        cols = [col for col in ["corp_code", "corp_name", "corp_name_eng", "stock_code", "year", "industry_code", "market"] if col in panel.columns]
        tasks = panel[cols].drop_duplicates(["corp_code", "year"]).copy()
    elif selected_path.exists():
        selected = pd.read_excel(selected_path, dtype={"corp_code": str, "stock_code": str})
        rows: List[Dict[str, Any]] = []
        for _, firm in selected.iterrows():
            years = parse_available_years(firm.get("available_english_annual_report_years"))
            if not years:
                years = list(range(config.start_year, config.end_year + 1))
            for year in years:
                if config.start_year <= year <= config.end_year:
                    row = firm.to_dict()
                    row["year"] = year
                    rows.append(row)
        tasks = pd.DataFrame(rows)
    else:
        raise FileNotFoundError(f"Cannot find {text_panel_path} or {selected_path}")

    tasks["corp_code"] = tasks["corp_code"].astype(str).str.zfill(8)
    tasks["stock_code"] = tasks["stock_code"].astype(str).str.zfill(6)
    tasks["year"] = pd.to_numeric(tasks["year"], errors="coerce").astype("Int64")
    tasks = tasks[tasks["year"].notna()].copy()
    tasks["year"] = tasks["year"].astype(int)
    tasks = tasks.drop_duplicates(["corp_code", "year"]).sort_values(["corp_code", "year"]).reset_index(drop=True)
    if config.sample_limit:
        tasks = tasks.head(config.sample_limit)
    return tasks


def parse_available_years(value: Any) -> List[int]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    return sorted({int(match) for match in re.findall(r"20\d{2}", str(value))})


def fetch_full_statement(client: OpenDartClient, corp_code: str, year: int) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    messages: List[str] = []
    for fs_div in ("CFS", "OFS"):
        data = client.get_json(
            "fnlttSinglAcntAll.json",
            {
                "corp_code": corp_code,
                "bsns_year": str(year),
                "reprt_code": ANNUAL_REPORT_CODE,
                "fs_div": fs_div,
            },
        )
        status = str(data.get("status", ""))
        message = str(data.get("message", ""))
        if status == "000" and data.get("list"):
            rows = data.get("list") or []
            for row in rows:
                row["selected_fs_div"] = fs_div
            return rows, fs_div, None
        messages.append(f"{fs_div}:{status} {message}".strip())
        if status not in {"000", "013", "014"}:
            return [], fs_div, "; ".join(messages)
    return [], "", "; ".join(messages)


def extract_financial_items(statement_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for variable, spec in FINANCIAL_ITEM_SPECS.items():
        value, account_id, account_name = choose_financial_value(statement_rows, spec)
        result[variable] = value
        result[f"{variable}_account_id"] = account_id
        result[f"{variable}_account_name"] = account_name
    return result


def build_financial_panel(config: Config) -> Tuple[pd.DataFrame, pd.DataFrame]:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    config.cache_dir.mkdir(parents=True, exist_ok=True)

    controls_path = config.out_dir / "06_financial_controls_panel.xlsx"
    raw_long_path = config.out_dir / "06_financial_statement_raw_long.xlsx"
    checkpoint_path = config.cache_dir / "financial_controls_checkpoint.csv"
    raw_checkpoint_path = config.cache_dir / "financial_statement_raw_long_checkpoint.csv"

    if controls_path.exists() and not config.refresh_financials:
        controls = pd.read_excel(controls_path, dtype={"corp_code": str, "stock_code": str})
        raw_long = pd.read_excel(raw_long_path, dtype={"corp_code": str, "stock_code": str}) if raw_long_path.exists() else pd.DataFrame()
        return controls, raw_long

    client = OpenDartClient(sleep_seconds=config.sleep_seconds, retries=config.retries)
    tasks = load_firm_year_tasks(config)

    completed: set[Tuple[str, int]] = set()
    control_rows: List[Dict[str, Any]] = []
    raw_rows: List[Dict[str, Any]] = []

    if checkpoint_path.exists() and not config.refresh_financials:
        previous = pd.read_csv(checkpoint_path, dtype={"corp_code": str, "stock_code": str})
        previous["year"] = pd.to_numeric(previous["year"], errors="coerce").astype("Int64")
        previous = previous[previous["year"].notna()].copy()
        previous["year"] = previous["year"].astype(int)
        control_rows = previous.to_dict("records")
        completed = {(str(row["corp_code"]).zfill(8), int(row["year"])) for row in control_rows}
        print(f"Loaded financial checkpoint: {len(control_rows):,} firm-years")
    if raw_checkpoint_path.exists() and not config.refresh_financials and config.save_raw_long:
        raw_previous = pd.read_csv(raw_checkpoint_path, dtype={"corp_code": str, "stock_code": str})
        raw_rows = raw_previous.to_dict("records")

    pending = [row for row in tasks.to_dict("records") if (str(row["corp_code"]).zfill(8), int(row["year"])) not in completed]

    for task in progress(pending, total=len(pending), desc="Fetching financial statements"):
        corp_code = str(task["corp_code"]).zfill(8)
        year = int(task["year"])
        statement_rows, selected_fs_div, error = fetch_full_statement(client, corp_code, year)
        extracted = extract_financial_items(statement_rows) if statement_rows else {}
        rcept_no = first_nonempty([row.get("rcept_no") for row in statement_rows])

        control_row = {
            **task,
            "year": year,
            "financial_fs_div": selected_fs_div,
            "financial_rcept_no": rcept_no,
            "financial_download_status": "ok" if statement_rows else "failed",
            "financial_download_error": error,
            **extracted,
        }
        control_rows.append(control_row)

        if config.save_raw_long:
            for row in statement_rows:
                raw_rows.append(
                    {
                        "corp_code": corp_code,
                        "stock_code": task.get("stock_code"),
                        "corp_name": task.get("corp_name"),
                        "year": year,
                        **row,
                    }
                )

        pd.DataFrame(control_rows).to_csv(checkpoint_path, index=False, encoding="utf-8-sig")
        if config.save_raw_long and raw_rows:
            pd.DataFrame(raw_rows).to_csv(raw_checkpoint_path, index=False, encoding="utf-8-sig")

    controls = pd.DataFrame(control_rows)
    controls = add_financial_ratios(controls)
    controls = order_financial_columns(controls)
    write_excel(controls, controls_path)

    raw_long = pd.DataFrame(raw_rows)
    if config.save_raw_long and not raw_long.empty:
        write_excel(raw_long, raw_long_path)

    return controls, raw_long


def first_nonempty(values: Sequence[Any]) -> Optional[Any]:
    for value in values:
        if value is not None and str(value).strip():
            return value
    return None


def add_financial_ratios(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for col in FINANCIAL_ITEM_SPECS:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    result = result.sort_values(["corp_code", "year"]).reset_index(drop=True)
    result["LagSales"] = result.groupby("corp_code")["Sales"].shift(1)
    result["LagTotalAssets"] = result.groupby("corp_code")["TotalAssets"].shift(1)
    result["AvgTotalAssets"] = (result["TotalAssets"] + result["LagTotalAssets"]) / 2

    result["Size"] = result["TotalAssets"].apply(safe_log)
    result["Leverage"] = [safe_divide(a, b) for a, b in zip(result["TotalLiabilities"], result["TotalAssets"])]
    result["ROA"] = [safe_divide(a, b) for a, b in zip(result["NetIncome"], result["TotalAssets"])]
    result["ROA_AvgAssets"] = [safe_divide(a, b) for a, b in zip(result["NetIncome"], result["AvgTotalAssets"])]
    result["ROE"] = [safe_divide(a, b) for a, b in zip(result["NetIncome"], result["TotalEquity"])]
    result["SalesGrowth"] = [
        safe_divide(current - previous, previous) if pd.notna(current) and pd.notna(previous) else None
        for current, previous in zip(result["Sales"], result["LagSales"])
    ]
    result["OperatingMargin"] = [safe_divide(a, b) for a, b in zip(result["OperatingIncome"], result["Sales"])]
    result["Liquidity"] = [safe_divide(a, b) for a, b in zip(result["CurrentAssets"], result["CurrentLiabilities"])]
    result["Tangibility"] = [safe_divide(a, b) for a, b in zip(result["PPE"], result["TotalAssets"])]
    result["CashHolding"] = [safe_divide(a, b) for a, b in zip(result["Cash"], result["TotalAssets"])]
    result["R&DIntensity"] = [safe_divide(a, b) for a, b in zip(result["R&DExpense"], result["Sales"])]
    result["CapexIntensity"] = [safe_divide(a, b) for a, b in zip(result["CAPEX"], result["TotalAssets"])]

    if "est_dt" in result.columns:
        est_year = result["est_dt"].astype(str).str.extract(r"(19\d{2}|20\d{2})", expand=False)
    elif "establishment_year" in result.columns:
        est_year = result["establishment_year"].astype(str).str.extract(r"(19\d{2}|20\d{2})", expand=False)
    else:
        est_year = pd.Series([None] * len(result))
    est_year_num = pd.to_numeric(est_year, errors="coerce")
    result["FirmAge"] = [
        math.log(1 + int(year) - int(est)) if pd.notna(est) and int(year) >= int(est) else None
        for year, est in zip(result["year"], est_year_num)
    ]
    return result


def order_financial_columns(df: pd.DataFrame) -> pd.DataFrame:
    preferred = [
        "corp_code",
        "corp_name",
        "corp_name_eng",
        "stock_code",
        "market",
        "industry_code",
        "year",
        "financial_fs_div",
        "financial_rcept_no",
        "financial_download_status",
        "financial_download_error",
        "TotalAssets",
        "TotalLiabilities",
        "TotalEquity",
        "EquityAttributableToOwners",
        "Sales",
        "OperatingIncome",
        "NetIncome",
        "CurrentAssets",
        "CurrentLiabilities",
        "Cash",
        "PPE",
        "R&DExpense",
        "CAPEX",
        "Size",
        "Leverage",
        "ROA",
        "ROA_AvgAssets",
        "ROE",
        "SalesGrowth",
        "OperatingMargin",
        "Liquidity",
        "Tangibility",
        "CashHolding",
        "R&DIntensity",
        "CapexIntensity",
        "FirmAge",
        "LagSales",
        "LagTotalAssets",
        "AvgTotalAssets",
    ]
    ordered = [col for col in preferred if col in df.columns]
    remaining = [col for col in df.columns if col not in ordered]
    return df[ordered + remaining]


def build_market_template(config: Config, controls: pd.DataFrame) -> pd.DataFrame:
    template_cols = [
        "corp_code",
        "corp_name",
        "stock_code",
        "year",
        "MarketCap",
        "MarketValueEquity",
        "YearEndPrice",
        "SharesOutstanding",
        "BookValueEquity",
        "TobinQ",
        "MarketToBook",
        "AnnualStockReturn",
        "CAR_filing_1_1",
        "CAR_filing_3_3",
        "market_data_source",
        "market_data_notes",
    ]
    template = controls[[col for col in ["corp_code", "corp_name", "stock_code", "year"] if col in controls.columns]].drop_duplicates()
    for col in template_cols:
        if col not in template.columns:
            template[col] = None
    template = template[template_cols]
    write_excel(template, config.out_dir / "07_market_value_panel_template.xlsx")
    return template


def build_pre_market_regression_dataset(config: Config, controls: pd.DataFrame) -> Optional[pd.DataFrame]:
    text_panel_path = config.out_dir / "04_digital_strategy_panel.xlsx"
    if not text_panel_path.exists():
        return None
    text = pd.read_excel(text_panel_path, dtype={"corp_code": str, "stock_code": str, "rcept_no": str})
    for frame in (text, controls):
        frame["corp_code"] = frame["corp_code"].astype(str).str.zfill(8)
        frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype("Int64")
    merged = text.merge(
        controls,
        on=["corp_code", "year"],
        how="left",
        suffixes=("", "_financial"),
    )
    if "MarketSignalDisclosure" in merged.columns and "BMI_Reconstruction" in merged.columns:
        merged["Digital_Hype_Gap"] = (
            merged["MarketSignalDisclosure"] - merged["BMI_Reconstruction"]
        ).clip(lower=0)
        merged["CredibleDigitalSignal"] = merged["DigitalStrategy"] - merged["Digital_Hype_Gap"]
        merged["DigitalStrategySquared"] = merged["DigitalStrategy"] ** 2
    write_excel(merged, config.out_dir / "08_final_regression_dataset_pre_market.xlsx")
    return merged


def doctor() -> int:
    print(f"Python executable: {sys.executable}")
    print(f"DART_API_KEY set: {bool(os.getenv('DART_API_KEY'))}")
    print(f"Default output directory: {SCRIPT_DIR / 'korea_digital_strategy_output'}")
    for module, package in REQUIRED_PIP_PACKAGES.items():
        print(f"{package}: {'OK' if importlib.util.find_spec(module) else 'MISSING'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=SCRIPT_DIR / "korea_digital_strategy_output")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--sleep-seconds", type=float, default=0.12)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--refresh-financials", action="store_true")
    parser.add_argument("--no-raw-long", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=None, help="Small test run limit for firm-years.")
    parser.add_argument("--doctor", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.doctor:
        return doctor()

    config = Config(
        out_dir=args.out_dir,
        start_year=args.start_year,
        end_year=args.end_year,
        sleep_seconds=args.sleep_seconds,
        retries=args.retries,
        refresh_financials=args.refresh_financials,
        save_raw_long=not args.no_raw_long,
        sample_limit=args.sample_limit,
    )
    try:
        controls, raw_long = build_financial_panel(config)
        build_market_template(config, controls)
        merged = build_pre_market_regression_dataset(config, controls)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Done.")
    print(f"Output directory: {config.out_dir.resolve()}")
    print(f"Financial controls rows: {len(controls):,}")
    print(f"Raw financial statement rows: {len(raw_long):,}")
    if merged is not None:
        print(f"Pre-market regression dataset rows: {len(merged):,}")
    else:
        print("Text panel not found yet; pre-market regression dataset was skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
