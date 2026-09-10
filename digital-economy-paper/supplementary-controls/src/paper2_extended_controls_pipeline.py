from __future__ import annotations

import concurrent.futures as futures
import getpass
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyhdfe
import requests
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.sandwich_covariance import cov_cluster


sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(
    os.getenv("PAPER2_OUTPUT_DIR", str(Path(__file__).resolve().parents[1]))
).resolve()
DATA_DIR = OUT / "01_新增控制变量数据"
RESULT_DIR = OUT / "02_模型结果"
CODE_DIR = OUT / "03_复现代码"
NOTE_DIR = OUT / "04_说明文档"
STATA_DIR = OUT / "05_Stata复核"

FROZEN_PANEL = Path(
    os.getenv(
        "PAPER2_FROZEN_PANEL",
        str(ROOT / "data" / "03_frozen_augmented_research_panel.csv"),
    )
)
PREVIOUS_INTERNAL_RESULTS = Path(
    os.getenv(
        "PAPER2_PREVIOUS_RESULTS",
        str(ROOT / "data" / "16_python_internal_model_results.csv"),
    )
)
OLD_180_FIRM_LONG = Path(
    os.getenv(
        "PAPER2_OLD_FINANCIAL_LONG",
        str(ROOT / "data" / "16_opendart_financial_raw_long.csv"),
    )
)

API_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
REPORT_CODE = "11011"
SUCCESS = "000"
NO_DATA = "013"

COMMON_CONTROLS = [
    "FirmSize_w",
    "Leverage_w",
    "ROA_AvgAssets_w",
    "SalesGrowth_w",
    "Liquidity_w",
    "OperatingMargin_w",
    "FirmAgeLog_w",
    "LossDummy",
    "NegativeEquityDummy",
    "LogTotalSentences",
    "FiscalYearStockReturn_w",
    "FiscalYearDailyVolatility_w",
]

BASE_CONTROLS = ["AssetTurnover_w", *COMMON_CONTROLS]

EXTENDED_CONTROL_DEFINITIONS = {
    "RAndDIntensity_OpenDART_w": {
        "name_ko": "연구개발집약도",
        "formula": "RAndDExpense / abs(Sales)",
        "meaning": "기업의 혁신투입 수준을 통제한다. 연구개발 역량이 높은 기업은 디지털 공시와 미래 효율성 모두에서 다르게 나타날 수 있다.",
    },
    "IntangibleAssetRatio_w": {
        "name_ko": "무형자산비율",
        "formula": "IntangibleAssets / TotalAssets",
        "meaning": "소프트웨어, 개발비, 지식자산 기반을 통제한다. BMIDisclosure가 기존 지식자산 축적의 대리변수인지 점검한다.",
    },
    "PPE_Ratio_w": {
        "name_ko": "유형자산비율",
        "formula": "PPE / TotalAssets",
        "meaning": "자산구조와 자본집약도를 통제한다. 자산회전율은 설비 비중이 높은 기업에서 구조적으로 달라질 수 있다.",
    },
    "OperatingCashFlowRatio_w": {
        "name_ko": "영업현금흐름비율",
        "formula": "OperatingCashFlow / TotalAssets",
        "meaning": "기업의 현금창출력과 실행여력을 통제한다. 디지털 전략을 실제로 추진할 내부 자금능력과 관련된다.",
    },
    "CapexIntensity_w": {
        "name_ko": "설비투자집약도",
        "formula": "abs(CAPEX) / TotalAssets",
        "meaning": "물적 투자 규모를 통제한다. 효율성 변화가 디지털 공시보다 투자지출에서 비롯될 가능성을 점검한다.",
    },
    "RAndDIntensityReported_w": {
        "name_ko": "보고서기재 연구개발비율",
        "formula": "reported R&D ratio from annual report text",
        "meaning": "OpenDART 손익계산서에서 연구개발비가 별도 계정으로 잡히지 않는 경우를 보완하는 텍스트 기반 통제변수다.",
    },
}

FINANCIAL_SPECS: dict[str, dict[str, Any]] = {
    "PPE": {
        "sj": ["BS"],
        "ids": ["ifrs-full_PropertyPlantAndEquipment", "ifrs_PropertyPlantAndEquipment"],
        "exact": ["유형자산", "property plant and equipment", "tangible assets"],
        "contains": ["propertyplantandequipment"],
    },
    "IntangibleAssets": {
        "sj": ["BS"],
        "ids": [
            "ifrs-full_IntangibleAssetsOtherThanGoodwill",
            "ifrs_IntangibleAssetsOtherThanGoodwill",
            "ifrs-full_IntangibleAssetsAndGoodwill",
            "dart_OtherIntangibleAssetsGross",
        ],
        "exact": ["무형자산", "intangible assets", "intangible assets other than goodwill"],
        "contains": ["무형자산", "intangibleassets"],
    },
    "CAPEX": {
        "sj": ["CF"],
        "ids": [
            "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            "ifrs_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            "ifrs-full_PaymentsToAcquirePropertyPlantAndEquipment",
            "ifrs_PaymentsToAcquirePropertyPlantAndEquipment",
            "dart_PurchaseOfOtherPropertyPlantAndEquipment",
        ],
        "exact": [
            "유형자산의취득",
            "유형자산취득",
            "purchase of property plant and equipment",
            "payments to acquire property plant and equipment",
        ],
        "contains": ["유형자산의취득", "유형자산취득", "paymentstoacquirepropertyplantandequipment"],
    },
    "OperatingCashFlow": {
        "sj": ["CF"],
        "ids": [
            "ifrs-full_CashFlowsFromUsedInOperatingActivities",
            "ifrs_CashFlowsFromUsedInOperatingActivities",
        ],
        "exact": [
            "영업활동현금흐름",
            "영업활동으로인한현금흐름",
            "cash flows from used in operating activities",
        ],
        "contains": [
            "영업활동현금흐름",
            "영업활동으로인한현금흐름",
            "cashflowsfromusedinoperatingactivities",
        ],
    },
    "RAndDExpense": {
        "sj": ["IS", "CIS"],
        "ids": ["dart_ResearchAndDevelopmentExpenses"],
        "exact": ["연구개발비", "연구비및개발비", "research and development expenses"],
        "contains": ["연구개발비", "researchanddevelopment"],
        "exclude": ["자산", "capitalized", "정부보조", "governmentgrant"],
    },
}


def ensure_dirs() -> None:
    for path in [OUT, DATA_DIR, RESULT_DIR, CODE_DIR, NOTE_DIR, STATA_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def normalize_code(value: Any, width: int) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(width) if digits else ""


def normalize_name(value: Any) -> str:
    return re.sub(r"[\s\W_]+", "", str(value or "").lower(), flags=re.UNICODE)


def parse_number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace(",", "").replace(" ", "")
    if not text or text in {"-", "nan", "None", "null"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float).replace([np.inf, -np.inf], np.nan)


def safe_divide(a: Any, b: Any) -> float | None:
    try:
        x, y = float(a), float(b)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y) or y == 0:
        return None
    return x / y


def winsor(series: pd.Series, tail: float = 0.01) -> pd.Series:
    values = number(series)
    valid = values.dropna()
    if valid.empty:
        return values
    lo, hi = valid.quantile([tail, 1 - tail])
    return values.clip(lo, hi)


def zscore(series: pd.Series) -> pd.Series:
    values = number(series)
    sd = values.std(ddof=1)
    if not np.isfinite(sd) or sd <= 0:
        return pd.Series(np.nan, index=series.index)
    return (values - values.mean()) / sd


def exact_lead(panel: pd.DataFrame, column: str, horizon: int) -> pd.Series:
    lookup = panel[["corp_code", "year", column]].copy()
    lookup["year"] = lookup["year"] - horizon
    lookup = lookup.rename(columns={column: "_lead_value"})
    matched = panel[["corp_code", "year"]].merge(
        lookup, on=["corp_code", "year"], how="left", sort=False, validate="one_to_one"
    )
    return matched["_lead_value"].set_axis(panel.index)


def select_financial_item(records: list[dict[str, Any]], spec: dict[str, Any]) -> dict[str, Any] | None:
    ids = [str(value).lower() for value in spec.get("ids", [])]
    exact = {normalize_name(value) for value in spec.get("exact", [])}
    contains = [normalize_name(value) for value in spec.get("contains", [])]
    excludes = [normalize_name(value) for value in spec.get("exclude", [])]
    statements = spec.get("sj", [])
    candidates: list[tuple[tuple[int, int, int, int], dict[str, Any]]] = []
    for record in records:
        sj_div = str(record.get("sj_div", ""))
        if sj_div not in statements:
            continue
        account_id = str(record.get("account_id", "")).lower()
        name = normalize_name(record.get("account_nm"))
        if any(token and token in name for token in excludes):
            continue
        if account_id in ids:
            match_rank = ids.index(account_id)
        elif name in exact:
            match_rank = 100
        elif any(token and token in name for token in contains):
            match_rank = 200
        else:
            continue
        amount = parse_number(record.get("thstrm_amount"))
        missing_rank = 1 if amount is None else 0
        sj_rank = statements.index(sj_div)
        try:
            order = int(float(record.get("ord", 999999)))
        except (TypeError, ValueError):
            order = 999999
        candidates.append(((match_rank, missing_rank, sj_rank, order), record))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def extract_accounts(payload: dict[str, Any], fs_div: str) -> dict[str, Any]:
    records = list(payload.get("list") or [])
    row: dict[str, Any] = {
        "financial_fs_div_requested": fs_div,
        "api_status": payload.get("status"),
        "api_message": payload.get("message"),
        "financial_record_count": len(records),
    }
    for variable, spec in FINANCIAL_SPECS.items():
        record = select_financial_item(records, spec)
        amount = parse_number(record.get("thstrm_amount")) if record else None
        if variable == "CAPEX" and amount is not None:
            amount = abs(amount)
        row[variable] = amount
        row[f"{variable}_account_id"] = record.get("account_id") if record else None
        row[f"{variable}_account_name"] = record.get("account_nm") if record else None
        row[f"{variable}_sj_div"] = record.get("sj_div") if record else None
        row[f"{variable}_currency"] = record.get("currency") if record else None
    return row


def request_one(session: requests.Session, api_key: str, corp_code: str, year: int, fs_div: str) -> dict[str, Any]:
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": REPORT_CODE,
        "fs_div": fs_div,
    }
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            response = session.get(API_URL, params=params, timeout=60)
            response.raise_for_status()
            payload = response.json()
            status = str(payload.get("status", ""))
            if status not in {SUCCESS, NO_DATA}:
                raise RuntimeError(f"OpenDART status {status}: {payload.get('message')}")
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(min(1.5 * attempt, 6))
    raise RuntimeError(str(last_error))


def fetch_extended_one(task: dict[str, Any], api_key: str) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": "KoreaDigitalDisclosurePaper2/1.0"})
    corp_code = str(task["corp_code"]).zfill(8)
    year = int(task["year"])
    hint = str(task.get("financial_fs_div") or "")
    fs_order = [hint] if hint in {"CFS", "OFS"} else ["CFS", "OFS"]
    errors = []
    for fs_div in fs_order:
        try:
            payload = request_one(session, api_key, corp_code, year, fs_div)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fs_div}:{exc}")
            continue
        if str(payload.get("status")) == NO_DATA:
            errors.append(f"{fs_div}:no_data")
            continue
        extracted = extract_accounts(payload, fs_div)
        extracted.update(
            {
                "corp_code": corp_code,
                "stock_code": str(task.get("stock_code") or "").zfill(6),
                "corp_name": task.get("corp_name"),
                "market": task.get("market"),
                "year": year,
                "preferred_fs_div_from_core_panel": hint,
                "opendart_error_note": "; ".join(errors),
                "retrieved_at": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
            }
        )
        return extracted
    row = {
        "corp_code": corp_code,
        "stock_code": str(task.get("stock_code") or "").zfill(6),
        "corp_name": task.get("corp_name"),
        "market": task.get("market"),
        "year": year,
        "preferred_fs_div_from_core_panel": hint,
        "financial_fs_div_requested": None,
        "api_status": None,
        "api_message": None,
        "financial_record_count": 0,
        "opendart_error_note": "; ".join(errors),
        "retrieved_at": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
    }
    for variable in FINANCIAL_SPECS:
        row[variable] = None
        row[f"{variable}_account_id"] = None
        row[f"{variable}_account_name"] = None
        row[f"{variable}_sj_div"] = None
        row[f"{variable}_currency"] = None
    return row


def collect_extended_controls(tasks: pd.DataFrame, api_key: str, workers: int) -> pd.DataFrame:
    checkpoint = DATA_DIR / "01_OpenDART扩展财务科目_checkpoint.csv"
    if checkpoint.exists():
        existing = pd.read_csv(checkpoint, dtype={"corp_code": str, "stock_code": str}, low_memory=False)
        existing["corp_code"] = existing["corp_code"].str.zfill(8)
        existing["year"] = pd.to_numeric(existing["year"], errors="coerce").astype("Int64")
    else:
        existing = pd.DataFrame()

    if not existing.empty:
        done = existing[["corp_code", "year"]].drop_duplicates().assign(_done=True)
        pending = tasks.merge(done, on=["corp_code", "year"], how="left")
        pending = pending[pending["_done"].isna()].drop(columns="_done")
    else:
        pending = tasks.copy()

    print(
        f"OpenDART extended accounts: total={len(tasks):,}, retained={len(existing):,}, pending={len(pending):,}",
        flush=True,
    )
    if pending.empty:
        return existing.drop_duplicates(["corp_code", "year"], keep="last")

    rows: list[dict[str, Any]] = []
    task_dicts = pending.to_dict("records")
    completed = 0
    with futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {executor.submit(fetch_extended_one, task, api_key): task for task in task_dicts}
        for future in futures.as_completed(future_map):
            completed += 1
            task = future_map[future]
            try:
                rows.append(future.result())
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "corp_code": str(task["corp_code"]).zfill(8),
                        "stock_code": str(task.get("stock_code") or "").zfill(6),
                        "corp_name": task.get("corp_name"),
                        "market": task.get("market"),
                        "year": int(task["year"]),
                        "preferred_fs_div_from_core_panel": task.get("financial_fs_div"),
                        "financial_fs_div_requested": None,
                        "api_status": None,
                        "api_message": None,
                        "financial_record_count": 0,
                        "opendart_error_note": f"worker_error:{exc}",
                        "retrieved_at": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
                    }
                )
            if completed == 1 or completed % 200 == 0 or completed == len(task_dicts):
                combined = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True, sort=False)
                combined = combined.drop_duplicates(["corp_code", "year"], keep="last")
                combined.to_csv(checkpoint, index=False, encoding="utf-8-sig")
                print(f"  collected {completed:,}/{len(task_dicts):,} pending", flush=True)
    final = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True, sort=False)
    final = final.drop_duplicates(["corp_code", "year"], keep="last")
    final.to_csv(checkpoint, index=False, encoding="utf-8-sig")
    return final


def load_panel() -> pd.DataFrame:
    required = [
        "corp_code",
        "corp_name",
        "stock_code",
        "market",
        "year",
        "industry_group",
        "financial_fs_div",
        "bmi_sentence_count",
        "substantive_digital_sentence_count",
        "total_sentences",
        "AssetTurnover",
        "RAndDIntensityReported",
        "EmployeeLog",
        "LargestHolderGroupOwnership",
        "OutsideDirectorRatio",
        "CurrentAssetRatio",
        *COMMON_CONTROLS,
        "TotalAssets",
        "Sales",
    ]
    available = pd.read_csv(FROZEN_PANEL, nrows=0).columns.tolist()
    columns = [column for column in dict.fromkeys(required) if column in available]
    panel = pd.read_csv(
        FROZEN_PANEL,
        usecols=columns,
        dtype={"corp_code": str, "stock_code": str},
        low_memory=False,
    )
    panel["corp_code"] = panel["corp_code"].str.zfill(8)
    panel["stock_code"] = panel["stock_code"].str.zfill(6)
    panel["year"] = pd.to_numeric(panel["year"], errors="raise").astype(int)
    panel = panel.sort_values(["corp_code", "year"]).reset_index(drop=True)

    total = number(panel["total_sentences"])
    bmi = number(panel["bmi_sentence_count"])
    substantive = number(panel["substantive_digital_sentence_count"])
    panel["BMI_share"] = bmi / total.where(total.gt(0))
    panel["NonBMI_share"] = (substantive - bmi).clip(lower=0) / total.where(total.gt(0))
    panel["BMI_component_z"] = zscore(panel["BMI_share"])
    panel["NonBMI_share_z"] = zscore(panel["NonBMI_share"])
    panel["BMIDisclosureAny"] = bmi.gt(0).astype(float)
    panel["Digital_share"] = substantive / total.where(total.gt(0))
    panel["Digital_share_z"] = zscore(panel["Digital_share"])
    panel["KOSDAQ"] = panel["market"].eq("KOSDAQ").astype(float)
    panel["BMI_x_KOSDAQ"] = panel["BMI_component_z"] * panel["KOSDAQ"]
    panel["AssetTurnover_w"] = winsor(panel["AssetTurnover"])
    panel["FutureAssetTurnover_h1"] = exact_lead(panel, "AssetTurnover_w", 1)
    panel["FutureAssetTurnover_h2"] = exact_lead(panel, "AssetTurnover_w", 2)
    panel["FutureAssetTurnover_h3"] = exact_lead(panel, "AssetTurnover_w", 3)
    panel["FutureBMI_h2"] = exact_lead(panel, "BMI_component_z", 2)
    panel["PastAssetTurnover_h1"] = exact_lead(panel, "AssetTurnover_w", -1)
    panel["PastAssetTurnover_h2"] = exact_lead(panel, "AssetTurnover_w", -2)
    panel["PreDisclosureTurnoverTrend"] = panel["PastAssetTurnover_h1"] - panel["PastAssetTurnover_h2"]
    panel["AssetTurnoverChange_h2"] = panel["FutureAssetTurnover_h2"] - panel["AssetTurnover_w"]

    for source, target in [
        ("RAndDIntensityReported", "RAndDIntensityReported_w"),
        ("EmployeeLog", "EmployeeLog_w"),
        ("LargestHolderGroupOwnership", "LargestHolderGroupOwnership_w"),
        ("OutsideDirectorRatio", "OutsideDirectorRatio_w"),
        ("CurrentAssetRatio", "CurrentAssetRatio_w"),
    ]:
        if source in panel:
            panel[target] = winsor(panel[source])
    return panel


def derive_extended_ratios(panel: pd.DataFrame, extended: pd.DataFrame) -> pd.DataFrame:
    extended = extended.copy()
    extended["corp_code"] = extended["corp_code"].astype(str).str.zfill(8)
    extended["year"] = pd.to_numeric(extended["year"], errors="coerce").astype("Int64")
    keep = [
        "corp_code",
        "year",
        "PPE",
        "IntangibleAssets",
        "CAPEX",
        "OperatingCashFlow",
        "RAndDExpense",
        "financial_fs_div_requested",
        "financial_record_count",
        "api_status",
        "api_message",
        "opendart_error_note",
    ]
    account_cols = [
        column
        for column in extended.columns
        if column.endswith("_account_id") or column.endswith("_account_name") or column.endswith("_sj_div")
    ]
    merged = panel.merge(
        extended[[column for column in [*keep, *account_cols] if column in extended.columns]],
        on=["corp_code", "year"],
        how="left",
        validate="one_to_one",
    )
    for column in ["PPE", "IntangibleAssets", "CAPEX", "OperatingCashFlow", "RAndDExpense", "TotalAssets", "Sales"]:
        if column in merged:
            merged[column] = pd.to_numeric(merged[column], errors="coerce")
    merged["PPE_Ratio"] = [safe_divide(a, b) for a, b in zip(merged["PPE"], merged["TotalAssets"])]
    merged["IntangibleAssetRatio"] = [
        safe_divide(a, b) for a, b in zip(merged["IntangibleAssets"], merged["TotalAssets"])
    ]
    merged["CapexIntensity"] = [safe_divide(abs(a), b) if pd.notna(a) else None for a, b in zip(merged["CAPEX"], merged["TotalAssets"])]
    merged["OperatingCashFlowRatio"] = [
        safe_divide(a, b) for a, b in zip(merged["OperatingCashFlow"], merged["TotalAssets"])
    ]
    merged["RAndDIntensity_OpenDART"] = [
        safe_divide(a, abs(b)) if pd.notna(a) and pd.notna(b) else None for a, b in zip(merged["RAndDExpense"], merged["Sales"])
    ]
    for variable in [
        "PPE_Ratio",
        "IntangibleAssetRatio",
        "CapexIntensity",
        "OperatingCashFlowRatio",
        "RAndDIntensity_OpenDART",
    ]:
        merged[f"{variable}_w"] = winsor(merged[variable])
    return merged


def drop_singletons(frame: pd.DataFrame, effects: list[str]) -> pd.DataFrame:
    output = frame.copy()
    while not output.empty:
        keep = np.ones(len(output), dtype=bool)
        for effect in effects:
            keep &= output.groupby(effect)[effect].transform("size").gt(1).to_numpy()
        if keep.all():
            break
        output = output.loc[keep].copy()
    return output


def fit_fwl(
    panel: pd.DataFrame,
    model_id: str,
    outcome: str,
    focals: list[str],
    controls: list[str],
    effects: list[str] = ["corp_code", "year"],
    sample: pd.Series | None = None,
    all_terms: bool = False,
) -> list[dict[str, Any]]:
    controls = [name for name in dict.fromkeys(controls) if name not in focals and name in panel.columns]
    required = [outcome, *focals, *controls, *effects, "corp_code", "year"]
    required = [name for name in dict.fromkeys(required) if name in panel.columns]
    mask = sample if sample is not None else pd.Series(True, index=panel.index)
    work = panel.loc[mask, required].replace([np.inf, -np.inf], np.nan).dropna().copy()
    work = drop_singletons(work, effects)
    names = [*focals, *controls]
    names = [name for name in names if name in work.columns]
    if work.empty or not names:
        return [
            {
                "model_id": model_id,
                "outcome": outcome,
                "term": term,
                "coefficient": np.nan,
                "std_error": np.nan,
                "p_value": np.nan,
                "ci95_low": np.nan,
                "ci95_high": np.nan,
                "N": 0,
                "firms": 0,
                "years": 0,
                "within_R2": np.nan,
                "effects": "+".join(effects),
                "cluster": "firm",
            }
            for term in focals
        ]
    matrix = work[[outcome, *names]].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    codes = np.column_stack([pd.Categorical(work[effect].astype(str)).codes for effect in effects])
    absorber = pyhdfe.create(
        codes,
        drop_singletons=False,
        compute_degrees=False,
        residualize_method="map",
        options={"transform": "symmetric", "acceleration": "cg", "tol": 1e-9},
    )
    transformed = absorber.residualize(matrix)
    y = transformed[:, 0]
    x_raw = transformed[:, 1:]
    selected_names: list[str] = []
    selected_arrays: list[np.ndarray] = []
    for name, values in zip(names, x_raw.T):
        if np.sqrt(np.mean(values**2)) <= 1e-10:
            continue
        trial = np.column_stack([*selected_arrays, values]) if selected_arrays else values.reshape(-1, 1)
        if np.linalg.matrix_rank(trial) > len(selected_arrays):
            selected_names.append(name)
            selected_arrays.append(values)
    if not selected_arrays:
        return []
    x = np.column_stack(selected_arrays)
    fitted = sm.OLS(y, x).fit()
    firm_codes = pd.Categorical(work["corp_code"].astype(str)).codes
    covariance = cov_cluster(fitted, firm_codes, use_correction=True)
    se = np.sqrt(np.maximum(np.diag(covariance), 0))
    dof = max(1, work["corp_code"].nunique() - 1)
    t_values = fitted.params / se
    p_values = 2 * stats.t.sf(np.abs(t_values), df=dof)
    critical = stats.t.ppf(0.975, dof)
    tss = float(np.sum(y**2))
    within_r2 = 1 - float(np.sum(fitted.resid**2)) / tss if tss > 0 else np.nan
    output_terms = selected_names if all_terms else focals
    rows = []
    for term in output_terms:
        if term not in selected_names:
            continue
        index = selected_names.index(term)
        rows.append(
            {
                "model_id": model_id,
                "outcome": outcome,
                "term": term,
                "coefficient": float(fitted.params[index]),
                "std_error": float(se[index]),
                "t_value": float(t_values[index]),
                "p_value": float(p_values[index]),
                "ci95_low": float(fitted.params[index] - critical * se[index]),
                "ci95_high": float(fitted.params[index] + critical * se[index]),
                "N": int(len(work)),
                "firms": int(work["corp_code"].nunique()),
                "years": int(work["year"].nunique()),
                "within_R2": float(within_r2),
                "effects": "+".join(effects),
                "cluster": "firm",
                "control_count": len(controls),
            }
        )
    return rows


def model_family(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    rows += fit_fwl(panel, "M00_BASELINE_REPRODUCED", "FutureAssetTurnover_h2", ["BMI_component_z"], BASE_CONTROLS, all_terms=True)
    rows += fit_fwl(panel, "M01_PLUS_RANDD_OPENDART", "FutureAssetTurnover_h2", ["BMI_component_z"], [*BASE_CONTROLS, "RAndDIntensity_OpenDART_w"], all_terms=True)
    rows += fit_fwl(panel, "M02_PLUS_INTANGIBLE", "FutureAssetTurnover_h2", ["BMI_component_z"], [*BASE_CONTROLS, "IntangibleAssetRatio_w"], all_terms=True)
    rows += fit_fwl(panel, "M03_PLUS_PPE", "FutureAssetTurnover_h2", ["BMI_component_z"], [*BASE_CONTROLS, "PPE_Ratio_w"], all_terms=True)
    rows += fit_fwl(panel, "M04_PLUS_OPERATING_CF", "FutureAssetTurnover_h2", ["BMI_component_z"], [*BASE_CONTROLS, "OperatingCashFlowRatio_w"], all_terms=True)
    rows += fit_fwl(panel, "M05_PLUS_CAPEX", "FutureAssetTurnover_h2", ["BMI_component_z"], [*BASE_CONTROLS, "CapexIntensity_w"], all_terms=True)
    rows += fit_fwl(
        panel,
        "M06_PLUS_HIGH_COVERAGE_EXTENDED",
        "FutureAssetTurnover_h2",
        ["BMI_component_z"],
        [*BASE_CONTROLS, "IntangibleAssetRatio_w", "PPE_Ratio_w", "OperatingCashFlowRatio_w", "CapexIntensity_w"],
        all_terms=True,
    )
    rows += fit_fwl(
        panel,
        "M07_PLUS_ALL_EXTENDED_WITH_RANDD",
        "FutureAssetTurnover_h2",
        ["BMI_component_z"],
        [
            *BASE_CONTROLS,
            "RAndDIntensity_OpenDART_w",
            "IntangibleAssetRatio_w",
            "PPE_Ratio_w",
            "OperatingCashFlowRatio_w",
            "CapexIntensity_w",
        ],
        all_terms=True,
    )
    if "RAndDIntensityReported_w" in panel.columns:
        rows += fit_fwl(
            panel,
            "M08_PLUS_REPORTED_RANDD_TEXT",
            "FutureAssetTurnover_h2",
            ["BMI_component_z"],
            [*BASE_CONTROLS, "RAndDIntensityReported_w"],
            all_terms=True,
        )
    rows += fit_fwl(
        panel,
        "M09_BMI_AND_NONBMI_DISCLOSURE",
        "FutureAssetTurnover_h2",
        ["BMI_component_z", "NonBMI_share_z"],
        BASE_CONTROLS,
        all_terms=True,
    )
    rows += fit_fwl(panel, "M10_ANY_BMI_DISCLOSURE", "FutureAssetTurnover_h2", ["BMIDisclosureAny"], BASE_CONTROLS, all_terms=True)
    rows += fit_fwl(panel, "M11_KOSPI_BASELINE", "FutureAssetTurnover_h2", ["BMI_component_z"], BASE_CONTROLS, sample=panel["KOSDAQ"].eq(0))
    rows += fit_fwl(panel, "M12_KOSDAQ_BASELINE", "FutureAssetTurnover_h2", ["BMI_component_z"], BASE_CONTROLS, sample=panel["KOSDAQ"].eq(1))
    rows += fit_fwl(panel, "M13_H1_BASELINE", "FutureAssetTurnover_h1", ["BMI_component_z"], BASE_CONTROLS)
    rows += fit_fwl(panel, "M14_H3_BASELINE", "FutureAssetTurnover_h3", ["BMI_component_z"], BASE_CONTROLS)
    rows += fit_fwl(panel, "M15_CHANGE_OUTCOME", "AssetTurnoverChange_h2", ["BMI_component_z"], COMMON_CONTROLS)
    rows += fit_fwl(panel, "M16_FUTURE_BMI_PLACEBO", "AssetTurnover_w", ["FutureBMI_h2"], COMMON_CONTROLS)
    rows += fit_fwl(panel, "M17_PRE_TREND_PLACEBO", "PreDisclosureTurnoverTrend", ["BMI_component_z"], ["PastAssetTurnover_h2"])
    results = pd.DataFrame(rows)
    focal_terms = {"BMI_component_z", "BMIDisclosureAny", "NonBMI_share_z", "FutureBMI_h2"}
    focal = results[results["term"].isin(focal_terms)].copy()
    valid = focal["p_value"].notna()
    if valid.any():
        focal.loc[valid, "q_BH_within_paper2"] = multipletests(focal.loc[valid, "p_value"], method="fdr_bh")[1]
        focal.loc[valid, "q_BY_within_paper2"] = multipletests(focal.loc[valid, "p_value"], method="fdr_by")[1]
    return results, focal


def coverage_tables(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    variables = [
        "BMI_share",
        "Digital_share",
        "AssetTurnover_w",
        "FutureAssetTurnover_h2",
        *BASE_CONTROLS,
        "RAndDIntensity_OpenDART_w",
        "IntangibleAssetRatio_w",
        "PPE_Ratio_w",
        "OperatingCashFlowRatio_w",
        "CapexIntensity_w",
        "RAndDIntensityReported_w",
        "EmployeeLog_w",
        "LargestHolderGroupOwnership_w",
        "OutsideDirectorRatio_w",
    ]
    variables = [name for name in dict.fromkeys(variables) if name in panel.columns]
    baseline_required = ["FutureAssetTurnover_h2", "BMI_component_z", *BASE_CONTROLS, "corp_code", "year"]
    baseline_sample = panel[baseline_required].replace([np.inf, -np.inf], np.nan).dropna().index
    rows = []
    for scope, subset in [("full_panel", panel), ("baseline_h2_sample_before_singleton_drop", panel.loc[baseline_sample])]:
        for variable in variables:
            values = subset[variable] if variable in subset.columns else pd.Series(dtype=float)
            rows.append(
                {
                    "scope": scope,
                    "variable": variable,
                    "rows": int(len(subset)),
                    "nonmissing": int(values.notna().sum()),
                    "missing": int(values.isna().sum()),
                    "coverage": float(values.notna().mean()) if len(subset) else np.nan,
                    "mean": float(number(values).mean()) if values.notna().any() else np.nan,
                    "median": float(number(values).median()) if values.notna().any() else np.nan,
                    "p01": float(number(values).quantile(0.01)) if values.notna().any() else np.nan,
                    "p99": float(number(values).quantile(0.99)) if values.notna().any() else np.nan,
                }
            )
    by_market = []
    for variable in [
        "RAndDIntensity_OpenDART_w",
        "IntangibleAssetRatio_w",
        "PPE_Ratio_w",
        "OperatingCashFlowRatio_w",
        "CapexIntensity_w",
        "RAndDIntensityReported_w",
    ]:
        if variable not in panel.columns:
            continue
        grouped = (
            panel.loc[baseline_sample]
            .groupby(["market", "year"], dropna=False)[variable]
            .agg(rows="size", nonmissing=lambda s: int(s.notna().sum()), mean="mean")
            .reset_index()
        )
        grouped["coverage"] = grouped["nonmissing"] / grouped["rows"]
        grouped.insert(0, "variable", variable)
        by_market.append(grouped)
    return pd.DataFrame(rows), pd.concat(by_market, ignore_index=True) if by_market else pd.DataFrame()


def account_audit(extended: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in extended.iterrows():
        for variable in FINANCIAL_SPECS:
            rows.append(
                {
                    "corp_code": str(row.get("corp_code")).zfill(8),
                    "stock_code": str(row.get("stock_code") or "").zfill(6),
                    "corp_name": row.get("corp_name"),
                    "market": row.get("market"),
                    "year": row.get("year"),
                    "variable": variable,
                    "amount": row.get(variable),
                    "fs_div": row.get("financial_fs_div_requested"),
                    "account_id": row.get(f"{variable}_account_id"),
                    "account_name": row.get(f"{variable}_account_name"),
                    "sj_div": row.get(f"{variable}_sj_div"),
                    "currency": row.get(f"{variable}_currency"),
                    "api_status": row.get("api_status"),
                    "source_api": "OpenDART fnlttSinglAcntAll annual report 11011",
                }
            )
    return pd.DataFrame(rows)


def write_excel_summary(tables: dict[str, pd.DataFrame], path: Path) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, df in tables.items():
            safe_sheet = sheet[:31]
            df.to_excel(writer, sheet_name=safe_sheet, index=False)
            ws = writer.book[safe_sheet]
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            for column_cells in ws.columns:
                max_len = min(48, max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells) + 2)
                ws.column_dimensions[column_cells[0].column_letter].width = max(10, max_len)


def make_markdown_report(
    coverage: pd.DataFrame,
    focal: pd.DataFrame,
    all_results: pd.DataFrame,
    extended: pd.DataFrame,
) -> str:
    def row(model: str, term: str = "BMI_component_z") -> pd.Series | None:
        hit = focal[focal["model_id"].eq(model) & focal["term"].eq(term)]
        return hit.iloc[0] if not hit.empty else None

    def fmt(model: str, term: str = "BMI_component_z") -> str:
        r = row(model, term)
        if r is None:
            return "未估计"
        return f"β={r['coefficient']:.6f}, SE={r['std_error']:.6f}, p={r['p_value']:.4g}, N={int(r['N']):,}, within R²={r['within_R2']:.4f}"

    ext_cov = coverage[
        coverage["scope"].eq("baseline_h2_sample_before_singleton_drop")
        & coverage["variable"].isin(
            [
                "RAndDIntensity_OpenDART_w",
                "IntangibleAssetRatio_w",
                "PPE_Ratio_w",
                "OperatingCashFlowRatio_w",
                "CapexIntensity_w",
                "RAndDIntensityReported_w",
            ]
        )
    ][["variable", "coverage", "nonmissing", "rows"]]
    coverage_lines = []
    for _, r in ext_cov.iterrows():
        coverage_lines.append(f"- `{r['variable']}`：覆盖率 {r['coverage']:.1%}，非缺失 {int(r['nonmissing']):,}/{int(r['rows']):,}")

    main = row("M00_BASELINE_REPRODUCED")
    high = row("M06_PLUS_HIGH_COVERAGE_EXTENDED")
    all_ext = row("M07_PLUS_ALL_EXTENDED_WITH_RANDD")
    nonbmi = row("M09_BMI_AND_NONBMI_DISCLOSURE", "NonBMI_share_z")
    anybmi = row("M10_ANY_BMI_DISCLOSURE", "BMIDisclosureAny")

    lines = [
        "# 论文2新增控制变量与模型增强说明",
        "",
        "## 一、处理范围",
        "",
        "本次不处理人工验证。处理范围包括 OpenDART 细分财务科目补抓、新增控制变量构造、缺失率审计、扩展控制变量模型、NonBMIDisclosure 对照、AnyBMIDisclosure 模型、滞后窗口、分市场和安慰剂检验复核。",
        "",
        "新增 OpenDART 科目来自 `fnlttSinglAcntAll` 年报接口，优先使用原核心财务面板中的 CFS/OFS 口径。变量只在能够从财务表识别到对应会计科目时取值，不把未识别科目自动填成 0。",
        "",
        "## 二、新增变量覆盖率",
        "",
        *coverage_lines,
        "",
        "解释上要特别注意：研发费用在 OpenDART 损益表中经常不作为统一标准科目单独列示，因此 `RAndDIntensity_OpenDART_w` 覆盖率通常会低于无形资产、固定资产和经营现金流。覆盖率不足时，它适合做补充检验，不适合强行进入主模型。",
        "",
        "## 三、核心结果",
        "",
        f"- 基准模型：{fmt('M00_BASELINE_REPRODUCED')}",
        f"- 加入无形资产、固定资产、经营现金流、CAPEX 四个高覆盖控制变量：{fmt('M06_PLUS_HIGH_COVERAGE_EXTENDED')}",
        f"- 加入全部 OpenDART 新增控制变量含研发强度：{fmt('M07_PLUS_ALL_EXTENDED_WITH_RANDD')}",
        f"- 同时控制 NonBMIDisclosure 后的 BMI 结果：{fmt('M09_BMI_AND_NONBMI_DISCLOSURE')}",
        f"- NonBMIDisclosure 自身结果：{fmt('M09_BMI_AND_NONBMI_DISCLOSURE', 'NonBMI_share_z')}",
        f"- AnyBMIDisclosure 虚拟变量模型：{fmt('M10_ANY_BMI_DISCLOSURE', 'BMIDisclosureAny')}",
        "",
        "## 四、结论判断",
        "",
    ]
    if main is not None and high is not None:
        if np.sign(main["coefficient"]) == np.sign(high["coefficient"]) and high["p_value"] < 0.05:
            lines.append("加入高覆盖新增控制变量后，BMIDisclosure 的方向保持为正且仍显著，说明主结果没有被企业资产结构、无形资产基础、经营现金流和资本开支完全解释。")
        elif np.sign(main["coefficient"]) == np.sign(high["coefficient"]):
            lines.append("加入高覆盖新增控制变量后，BMIDisclosure 的方向仍为正，但显著性有所下降。此时应把结果解释为对扩展控制变量有一定敏感性，而不是完全稳健的因果效应。")
        else:
            lines.append("加入高覆盖新增控制变量后，BMIDisclosure 的方向发生变化。此时主结论必须降级，说明原结果可能受到资产结构或经营质量差异影响。")
    if all_ext is not None and int(all_ext["N"]) < int(main["N"] * 0.7 if main is not None else 0):
        lines.append("包含 OpenDART 研发强度的全扩展模型样本损失较大，因此不建议把它作为主模型，只适合放在补充稳健性检验中。")
    if nonbmi is not None:
        if nonbmi["p_value"] >= 0.05:
            lines.append("NonBMIDisclosure 在同一模型中不显著时，可以强化论文逻辑：并不是所有数字披露都对应未来效率变化，和商业模式重构相关的披露更关键。")
        else:
            lines.append("NonBMIDisclosure 在同一模型中也显著时，论文应谨慎区分 BMI 机制与一般数字披露机制，不能只强调 BMI 一条路径。")
    if anybmi is not None:
        lines.append("AnyBMIDisclosure 模型用于判断有无披露是否已经足够解释结果；连续强度模型则用于判断披露比例的边际变化。两者结论应配合解释。")
    lines.extend(
        [
            "",
            "## 五、写作建议",
            "",
            "正文主模型仍建议使用基础控制变量，因为它覆盖率高、样本稳定、解释清楚。新增 OpenDART 控制变量建议作为扩展控制稳健性表呈现。若新增变量使样本明显下降，应在表下注明样本变化，不能只保留显著结果。",
            "",
            "本文可以写成：商业模式导向数字披露与未来经营效率存在稳定正向关系；该关系在控制资产结构、无形资产基础、经营现金流和资本开支后仍需检验，并根据扩展结果控制解释强度。不能写成：数字化披露已经被证明导致企业效率提高。",
        ]
    )
    return "\n".join(lines)


def prepare_stata(panel: pd.DataFrame, results: pd.DataFrame) -> None:
    variables = [
        "corp_code",
        "year",
        "FutureAssetTurnover_h2",
        "BMI_component_z",
        *BASE_CONTROLS,
        "RAndDIntensity_OpenDART_w",
        "IntangibleAssetRatio_w",
        "PPE_Ratio_w",
        "OperatingCashFlowRatio_w",
        "CapexIntensity_w",
        "NonBMI_share_z",
        "BMIDisclosureAny",
        "KOSDAQ",
    ]
    variables = [variable for variable in dict.fromkeys(variables) if variable in panel.columns]
    stata_data = panel[variables].copy()
    for column in stata_data.columns:
        if column != "corp_code":
            stata_data[column] = pd.to_numeric(stata_data[column], errors="coerce")
    dta_path = STATA_DIR / "paper2_stata_validation_sample.dta"
    stata_data.to_stata(dta_path, write_index=False, version=118)

    result_path = (STATA_DIR / "paper2_stata_results.dta").as_posix()
    csv_path = (STATA_DIR / "paper2_stata_results.csv").as_posix()
    dta_posix = dta_path.as_posix()
    do_path = STATA_DIR / "paper2_stata_validation.do"
    do_text = f'''
clear all
set more off
use "{dta_posix}", clear
egen firm_id = group(corp_code)
tempname handle
postfile `handle' str40 model str40 term double coefficient std_error p_value N firms years r2_within using "{result_path}", replace

local base AssetTurnover_w FirmSize_w Leverage_w ROA_AvgAssets_w SalesGrowth_w Liquidity_w OperatingMargin_w FirmAgeLog_w LossDummy NegativeEquityDummy LogTotalSentences FiscalYearStockReturn_w FiscalYearDailyVolatility_w

quietly reghdfe FutureAssetTurnover_h2 BMI_component_z `base', absorb(firm_id year) vce(cluster firm_id)
post `handle' ("M00_BASELINE_REPRODUCED") ("BMI_component_z") (_b[BMI_component_z]) (_se[BMI_component_z]) (2*ttail(e(df_r),abs(_b[BMI_component_z]/_se[BMI_component_z]))) (e(N)) (e(N_clust)) (.) (e(r2_within))

quietly reghdfe FutureAssetTurnover_h2 BMI_component_z IntangibleAssetRatio_w PPE_Ratio_w OperatingCashFlowRatio_w CapexIntensity_w `base', absorb(firm_id year) vce(cluster firm_id)
post `handle' ("M06_HIGH_COVERAGE") ("BMI_component_z") (_b[BMI_component_z]) (_se[BMI_component_z]) (2*ttail(e(df_r),abs(_b[BMI_component_z]/_se[BMI_component_z]))) (e(N)) (e(N_clust)) (.) (e(r2_within))

quietly reghdfe FutureAssetTurnover_h2 BMI_component_z RAndDIntensity_OpenDART_w IntangibleAssetRatio_w PPE_Ratio_w OperatingCashFlowRatio_w CapexIntensity_w `base', absorb(firm_id year) vce(cluster firm_id)
post `handle' ("M07_ALL_EXTENDED") ("BMI_component_z") (_b[BMI_component_z]) (_se[BMI_component_z]) (2*ttail(e(df_r),abs(_b[BMI_component_z]/_se[BMI_component_z]))) (e(N)) (e(N_clust)) (.) (e(r2_within))

quietly reghdfe FutureAssetTurnover_h2 BMI_component_z NonBMI_share_z `base', absorb(firm_id year) vce(cluster firm_id)
post `handle' ("M09_BMI_AND_NONBMI") ("BMI_component_z") (_b[BMI_component_z]) (_se[BMI_component_z]) (2*ttail(e(df_r),abs(_b[BMI_component_z]/_se[BMI_component_z]))) (e(N)) (e(N_clust)) (.) (e(r2_within))
post `handle' ("M09_BMI_AND_NONBMI") ("NonBMI_share_z") (_b[NonBMI_share_z]) (_se[NonBMI_share_z]) (2*ttail(e(df_r),abs(_b[NonBMI_share_z]/_se[NonBMI_share_z]))) (e(N)) (e(N_clust)) (.) (e(r2_within))

quietly reghdfe FutureAssetTurnover_h2 BMIDisclosureAny `base', absorb(firm_id year) vce(cluster firm_id)
post `handle' ("M10_ANY_BMI") ("BMIDisclosureAny") (_b[BMIDisclosureAny]) (_se[BMIDisclosureAny]) (2*ttail(e(df_r),abs(_b[BMIDisclosureAny]/_se[BMIDisclosureAny]))) (e(N)) (e(N_clust)) (.) (e(r2_within))

postclose `handle'
use "{result_path}", clear
export delimited using "{csv_path}", replace
exit, clear
'''
    do_path.write_text(do_text.strip() + "\n", encoding="utf-8")
    stata_exe = Path(r"C:\Program Files\Stata18\StataMP-64.exe")
    if stata_exe.exists():
        log_path = STATA_DIR / "paper2_stata_validation.log"
        subprocess.run([str(stata_exe), "-b", "do", str(do_path)], cwd=str(STATA_DIR), timeout=600)
        default_log = STATA_DIR / "paper2_stata_validation.log"
        if default_log.exists():
            print(f"Stata log: {default_log}", flush=True)
    else:
        print("Stata executable not found; do-file prepared only.", flush=True)


def write_outputs(panel: pd.DataFrame, extended: pd.DataFrame, coverage: pd.DataFrame, by_market: pd.DataFrame, results: pd.DataFrame, focal: pd.DataFrame) -> None:
    account_rows = account_audit(extended)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    account_rows.to_csv(DATA_DIR / "02_OpenDART扩展科目选择明细.csv", index=False, encoding="utf-8-sig")
    panel.to_csv(DATA_DIR / "03_加入新增控制变量后的研究面板.csv", index=False, encoding="utf-8-sig")
    coverage.to_csv(DATA_DIR / "04_新增控制变量缺失率与描述统计.csv", index=False, encoding="utf-8-sig")
    by_market.to_csv(DATA_DIR / "05_新增控制变量按市场年份覆盖率.csv", index=False, encoding="utf-8-sig")
    results.to_csv(RESULT_DIR / "01_扩展控制变量完整回归结果.csv", index=False, encoding="utf-8-sig")
    focal.to_csv(RESULT_DIR / "02_核心系数与FDR结果.csv", index=False, encoding="utf-8-sig")
    write_excel_summary(
        {
            "核心系数": focal,
            "完整回归": results,
            "缺失率": coverage,
            "市场年份覆盖率": by_market,
            "变量定义": pd.DataFrame(
                [
                    {"variable": key, **value}
                    for key, value in EXTENDED_CONTROL_DEFINITIONS.items()
                ]
            ),
            "OpenDART科目明细": account_rows.head(100000),
        },
        OUT / "论文2_新增控制变量与模型增强结果.xlsx",
    )
    report = make_markdown_report(coverage, focal, results, extended)
    (NOTE_DIR / "新增控制变量与模型增强说明.md").write_text(report, encoding="utf-8")


def summarize_to_console(focal: pd.DataFrame, coverage: pd.DataFrame) -> None:
    print("\n=== Paper2 focal model results ===", flush=True)
    display = focal[
        [
            "model_id",
            "term",
            "coefficient",
            "std_error",
            "p_value",
            "q_BH_within_paper2",
            "q_BY_within_paper2",
            "N",
            "firms",
            "within_R2",
        ]
    ].copy()
    print(display.to_string(index=False), flush=True)
    print("\n=== Added control coverage in baseline h2 sample ===", flush=True)
    cov = coverage[
        coverage["scope"].eq("baseline_h2_sample_before_singleton_drop")
        & coverage["variable"].isin(
            [
                "RAndDIntensity_OpenDART_w",
                "IntangibleAssetRatio_w",
                "PPE_Ratio_w",
                "OperatingCashFlowRatio_w",
                "CapexIntensity_w",
                "RAndDIntensityReported_w",
            ]
        )
    ][["variable", "nonmissing", "rows", "coverage", "mean", "median"]]
    print(cov.to_string(index=False), flush=True)


def main() -> int:
    ensure_dirs()
    shutil.copy2(Path(__file__), CODE_DIR / "paper2_extended_controls_pipeline.py")
    panel = load_panel()
    baseline_keys = panel[
        ["FutureAssetTurnover_h2", "BMI_component_z", *BASE_CONTROLS, "corp_code", "year"]
    ].replace([np.inf, -np.inf], np.nan).dropna().index
    tasks = panel.loc[
        baseline_keys,
        ["corp_code", "stock_code", "corp_name", "market", "year", "financial_fs_div"],
    ].drop_duplicates(["corp_code", "year"]).copy()

    api_key = os.getenv("DART_API_KEY", "").strip()
    if not api_key:
        api_key = getpass.getpass("Enter your OpenDART API key for Paper2 extended controls: ").strip()
    if not api_key:
        raise SystemExit("DART_API_KEY is required.")

    extended = collect_extended_controls(tasks, api_key, workers=int(os.getenv("PAPER2_WORKERS", "6")))
    extended.to_csv(DATA_DIR / "01_OpenDART扩展财务科目.csv", index=False, encoding="utf-8-sig")
    panel2 = derive_extended_ratios(panel, extended)
    coverage, by_market = coverage_tables(panel2)
    results, focal = model_family(panel2)
    write_outputs(panel2, extended, coverage, by_market, results, focal)
    prepare_stata(panel2, results)
    if (STATA_DIR / "paper2_stata_results.csv").exists():
        stata = pd.read_csv(STATA_DIR / "paper2_stata_results.csv", low_memory=False)
        stata.to_csv(RESULT_DIR / "03_Stata核心模型复核结果.csv", index=False, encoding="utf-8-sig")
    summarize_to_console(focal, coverage)
    print(f"\nOutput folder: {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
