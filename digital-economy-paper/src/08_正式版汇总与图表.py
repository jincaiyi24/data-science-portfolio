from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "outputs" / "韩国数字化战略论文_正式版_20260816"
DATA = FINAL / "01_核心数据"
RESULT = FINAL / "02_模型与结果"
POLICY = FINAL / "05_政策与识别资料"
REFS = FINAL / "07_参考文献"
README = FINAL / "00_阅读说明"
WORK = ROOT / "work" / "formal_final_20260816"


SOURCES = [
    {
        "type": "official_policy",
        "title": "Manufacturing Innovation 3.0 Strategy",
        "organization": "Republic of Korea Policy Briefing",
        "year": 2014,
        "use": "Policy background; predates the 2015 sample and is not a usable within-sample shock.",
        "url": "https://m.korea.kr/briefing/policyBriefingView.do?newsId=148780561",
    },
    {
        "type": "official_policy",
        "title": "Korean New Deal / Digital New Deal",
        "organization": "Ministry of Economy and Finance",
        "year": 2020,
        "use": "National digital-policy timing; unsuitable for a simple post-2020 DiD because it coincides with COVID-19 and has no untreated national group.",
        "url": "https://www.moef.go.kr/nw/nes/detailNesDtaView.do?menuNo=4010100&searchBbsId1=MOSFBBS_000000000028&searchNttId1=MOSF_000000000040637",
    },
    {
        "type": "official_policy",
        "title": "Korean New Deal English policy document",
        "organization": "Ministry of Economy and Finance",
        "year": 2020,
        "use": "English description of the Digital New Deal.",
        "url": "https://english.moef.go.kr/co/fixFileDown.do?orgNm=Korean_New_Deal.pdf",
    },
    {
        "type": "official_evaluation",
        "title": "Digital Transformation Policy Analysis",
        "organization": "National Assembly Budget Office",
        "year": 2023,
        "use": "Program scale and annual smart-factory implementation counts for 2014-2022.",
        "url": "https://nabo.go.kr/board/file/down.do?fid=33317567",
    },
    {
        "type": "official_program",
        "title": "Smart Factory Support Portal",
        "organization": "KOSMO / Ministry of SMEs and Startups",
        "year": 2026,
        "use": "Potential firm-level beneficiary verification; requires business registration number.",
        "url": "https://www.smart-factory.kr/",
    },
    {
        "type": "research",
        "title": "Smart Policies for Smart Factories",
        "organization": "Korea Development Institute",
        "year": 2019,
        "use": "Korean smart-factory policy design and evaluation background.",
        "url": "https://www.kdi.re.kr/eng/research/reportView?pub_no=16563",
    },
    {
        "type": "research_data_route",
        "title": "Regional factors associated with smart factory adoption in South Korea",
        "organization": "Technology in Society",
        "year": 2024,
        "use": "Documents MSS microdata with adoption year/type/level/location for supported firms during 2014-2020; strongest candidate for staggered treatment matching.",
        "url": "https://www.sciencedirect.com/science/article/pii/S0160791X24000575",
    },
    {
        "type": "official_disclosure",
        "title": "DART periodic-disclosure filing deadlines",
        "organization": "Financial Supervisory Service",
        "year": 2026,
        "use": "Annual reports are due within 90 days after fiscal year-end, explaining concentrated filing dates and bundled event-window information.",
        "url": "https://dart2.fss.or.kr/introduction/content2.do",
    },
    {
        "type": "market_structure",
        "title": "OECD Corporate Governance Factbook 2025: Korea",
        "organization": "OECD",
        "year": 2025,
        "use": "Benchmarks Korea's public-equity ownership structure against OECD members and documents the comparatively high corporate ownership share and low institutional-investor share.",
        "url": "https://www.oecd.org/en/publications/oecd-corporate-governance-factbook-2025_4d9f40fc-en/korea_42075190-en.html",
    },
    {
        "type": "official_market_policy",
        "title": "Corporate Value-up Plan",
        "organization": "Financial Services Commission",
        "year": 2024,
        "use": "Official evidence that Korean market reform emphasizes concrete value drivers, shareholder communication and returns in addressing the Korea discount.",
        "url": "https://www.fsc.go.kr/eng/po110101/82795",
    },
    {
        "type": "market_structure",
        "title": "Reforming large business groups to promote productivity and inclusion in Korea",
        "organization": "OECD Economic Survey: Korea",
        "year": 2018,
        "use": "Links concentrated control, governance concerns and affiliated-group structures to the Korea discount and weaker minority-shareholder valuation.",
        "url": "https://www.oecd.org/en/publications/oecd-economic-surveys-korea-2018_eco_surveys-kor-2018-en/full-report/component-8.html",
    },
    {
        "type": "digital_complementarity",
        "title": "Americans Do IT Better: US Multinationals and the Productivity Miracle",
        "organization": "American Economic Review",
        "year": 2012,
        "use": "Shows that IT productivity depends on complementary organization and management practices, so technology language or expenditure alone need not generate performance.",
        "url": "https://www.nber.org/papers/w13085",
    },
    {
        "type": "korea_smart_manufacturing",
        "title": "Are smart manufacturing systems beneficial for all SMEs? Evidence from Korea",
        "organization": "Management Decision",
        "year": 2022,
        "use": "Finds positive effects for actual smart-manufacturing maturity in 163 Korean manufacturing SMEs, but effects depend on industry and workforce composition.",
        "url": "https://www.sciencedirect.com/science/article/pii/S002517472200060X",
    },
    {
        "type": "korea_digital_maturity",
        "title": "How does digitalization drive urban industrial locations? An empirical examination of South Korea's experience",
        "organization": "Technology in Society",
        "year": 2024,
        "use": "Reports that most supported Korean smart factories remained at basic or lower-intermediate maturity, helping explain threshold and heterogeneous effects.",
        "url": "https://www.sciencedirect.com/science/article/pii/S0160791X24002562",
    },
    {
        "type": "method",
        "title": "Difference-in-Differences with multiple time periods",
        "organization": "Journal of Econometrics",
        "year": 2021,
        "use": "Callaway-Sant'Anna staggered-adoption estimator.",
        "url": "https://doi.org/10.1016/j.jeconom.2020.12.001",
    },
    {
        "type": "method",
        "title": "Estimating dynamic treatment effects in event studies with heterogeneous treatment effects",
        "organization": "Journal of Econometrics",
        "year": 2021,
        "use": "Sun-Abraham cohort-relative-time event-study estimator.",
        "url": "https://doi.org/10.1016/j.jeconom.2020.09.006",
    },
    {
        "type": "method",
        "title": "Estimating standard errors in finance panel data sets",
        "organization": "Review of Financial Studies",
        "year": 2009,
        "use": "Clustered standard-error guidance.",
        "url": "https://academic.oup.com/rfs/article-abstract/22/1/435/1585940",
    },
    {
        "type": "method",
        "title": "Event Studies in Economics and Finance",
        "organization": "Journal of Economic Literature",
        "year": 1997,
        "use": "Event-study design and interpretation.",
        "url": "https://www.jstor.org/stable/2729691",
    },
    {
        "type": "digital_transformation_review",
        "title": "A Systematic Review of the Literature on Digital Transformation",
        "organization": "Journal of Management Studies",
        "year": 2021,
        "use": "Conceptual positioning of digital transformation as organizational change rather than keyword prevalence.",
        "url": "https://onlinelibrary.wiley.com/doi/10.1111/joms.12639",
    },
]


def safe_read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False, dtype={"corp_code": str, "stock_code": str, "rcept_no": str})


def clean_record(record: dict) -> dict:
    result = {}
    for key, value in record.items():
        if pd.isna(value):
            result[key] = None
        elif isinstance(value, (np.integer,)):
            result[key] = int(value)
        elif isinstance(value, (np.floating,)):
            result[key] = float(value)
        else:
            result[key] = value
    return result


def select_rows(frame: pd.DataFrame, ids: list[str], focal_contains: str = "Digital") -> list[dict]:
    selected = frame.loc[frame["model_id"].isin(ids)].copy()
    if focal_contains and "focal" in selected:
        selected = selected.loc[selected["focal"].astype(str).str.contains(focal_contains, case=False, na=False)]
    cols = [
        c
        for c in [
            "model_id",
            "description",
            "outcome",
            "focal",
            "coefficient",
            "std_error",
            "p_value",
            "fdr_within_family",
            "fdr_concurrent_family",
            "n",
            "firms",
            "r_squared_within",
            "control_count",
            "effect_spec",
            "covariance",
            "sample_note",
        ]
        if c in selected.columns
    ]
    return [clean_record(row) for row in selected[cols].to_dict("records")]


def build_summary() -> dict:
    panel = safe_read_csv(DATA / "01_冻结分析面板_22654公司年度.csv")
    operating = safe_read_csv(RESULT / "01A_经营绩效完整模型结果.csv")
    car = safe_read_csv(RESULT / "01B_CAR完整模型结果.csv")
    joint = safe_read_csv(RESULT / "01C_非线性与联合检验.csv")
    temporal = safe_read_csv(RESULT / "05_文本时间边界稳健性.csv")
    concurrent = safe_read_csv(RESULT / "03_剔除并发公告后的CAR模型.csv")
    concurrent_summary = json.loads((RESULT / "04_并发公告审计摘要.json").read_text(encoding="utf-8"))
    audit = json.loads((RESULT / "06_最终模型审计摘要.json").read_text(encoding="utf-8"))

    digital = pd.to_numeric(panel["DigitalStrategy"], errors="coerce")
    year_counts = panel.groupby("year", as_index=False).agg(
        observations=("corp_code", "size"),
        firms=("corp_code", "nunique"),
        digital_mean=("DigitalStrategy", "mean"),
        positive_digital_share=("DigitalStrategy", lambda x: pd.to_numeric(x, errors="coerce").gt(0).mean()),
    )
    market_counts = panel.groupby("market", dropna=False, as_index=False).agg(
        observations=("corp_code", "size"), firms=("corp_code", "nunique")
    )
    summary = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "sample": {
            "rows": int(len(panel)),
            "firms": int(panel["corp_code"].nunique()),
            "years": [int(panel["year"].min()), int(panel["year"].max())],
            "duplicate_firm_years": int(panel.duplicated(["corp_code", "year"]).sum()),
            "digital_zero_share": float(digital.fillna(0).eq(0).mean()),
            "digital_mean": float(digital.mean()),
            "digital_std": float(digital.std()),
            "digital_p50": float(digital.quantile(0.5)),
            "digital_p75": float(digital.quantile(0.75)),
            "digital_p90": float(digital.quantile(0.90)),
            "digital_p99": float(digital.quantile(0.99)),
            "year_counts": [clean_record(x) for x in year_counts.to_dict("records")],
            "market_counts": [clean_record(x) for x in market_counts.to_dict("records")],
        },
        "operating_core": select_rows(
            operating,
            ["OP_CORE_SalesGrowth_w_t1", "OP_CORE_ROA_AvgAssets_w_t1", "OP_CORE_OperatingMargin_w_t1"],
        ),
        "car_core": select_rows(
            car,
            [
                "CAR_YEAR_FE_FIRM_CLUSTER",
                "CAR_EVENT_DATE_FE_FIRM_CLUSTER",
                "CAR_EVENT_DATE_FE_TWO_WAY",
                "CAR_EVENT_DATE_FE_LAGGED_CONTROLS",
                "CAR_MARKET_DATE_FE_TWO_WAY",
                "CAR_SAMPLE_KOSPI",
                "CAR_SAMPLE_KOSDAQ",
            ],
        ),
        "car_diagnostics": select_rows(
            car,
            [
                "CAR_PLACEBO_LEAD_LEVEL",
                "CAR_PLACEBO_LEAD_CHANGE",
                "CAR_EXPOSURE_PURE_SIGNAL",
                "CAR_EXPOSURE_INTERNAL_COMPONENTS",
                "CAR_EXPOSURE_BOILERPLATE",
                "CAR_EXPOSURE_MARKET_INTERACTION",
            ],
            focal_contains="",
        ),
        "joint_tests": [clean_record(x) for x in joint.to_dict("records")],
        "temporal_tests": [clean_record(x) for x in temporal.to_dict("records")],
        "concurrent_models": select_rows(
            concurrent,
            ["CONCURRENT_FULL_AlignedCAR_0_p2_w", "CONCURRENT_VERIFIED_FULL_AlignedCAR_0_p2_w", "CONCURRENT_CLEAN_ANY_AlignedCAR_0_p2_w", "CONCURRENT_CLEAN_HIGH_AlignedCAR_0_p2_w", "CONCURRENT_CLEAN_SAMEDAY_AlignedCAR_0_p2_w"],
        ),
        "concurrent_summary": concurrent_summary,
        "audit": audit,
        "sources": SOURCES,
    }
    return summary


def save_figures(summary: dict) -> None:
    figure_dir = RESULT / "图表"
    figure_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.unicode_minus": False})

    years = pd.DataFrame(summary["sample"]["year_counts"])
    fig, ax1 = plt.subplots(figsize=(8.2, 4.5), dpi=180)
    ax1.plot(years["year"], 100 * years["digital_mean"], color="#1F4D78", marker="o", linewidth=2, label="Mean DigitalStrategy (%)")
    ax1.set_ylabel("Mean substantive digital sentences (%)", color="#1F4D78")
    ax1.tick_params(axis="y", labelcolor="#1F4D78")
    ax1.set_xlabel("Fiscal year")
    ax1.grid(axis="y", color="#D9E0E7", linewidth=0.7)
    ax2 = ax1.twinx()
    ax2.plot(years["year"], 100 * years["positive_digital_share"], color="#B05A3C", marker="s", linewidth=1.8, label="Positive disclosure share")
    ax2.set_ylabel("Firm-years with substantive disclosure (%)", color="#B05A3C")
    ax2.tick_params(axis="y", labelcolor="#B05A3C")
    ax1.set_title("Digital-strategy disclosure over time")
    fig.tight_layout()
    fig.savefig(figure_dir / "01_数字化战略年度趋势.png", bbox_inches="tight")
    plt.close(fig)

    core = pd.DataFrame(summary["operating_core"] + [x for x in summary["car_core"] if x["model_id"] == "CAR_EVENT_DATE_FE_TWO_WAY"])
    labels = {
        "SalesGrowth_w_t1": "Sales growth t+1",
        "ROA_AvgAssets_w_t1": "ROA t+1",
        "OperatingMargin_w_t1": "Operating margin t+1",
        "AlignedCAR_0_p2_w": "CAR [0,+2]",
    }
    core["label"] = core["outcome"].map(labels).fillna(core["outcome"])
    fig, ax = plt.subplots(figsize=(8.2, 4.5), dpi=180)
    y = np.arange(len(core))
    ax.errorbar(core["coefficient"], y, xerr=1.96 * core["std_error"], fmt="o", color="#1F4D78", ecolor="#6B8499", capsize=4)
    ax.axvline(0, color="#555555", linewidth=1)
    ax.set_yticks(y, core["label"])
    ax.invert_yaxis()
    ax.set_xlabel("Coefficient on standardized DigitalStrategy (95% CI)")
    ax.set_title("Preferred-model estimates")
    ax.grid(axis="x", color="#D9E0E7", linewidth=0.7)
    fig.tight_layout()
    fig.savefig(figure_dir / "02_最终模型系数图.png", bbox_inches="tight")
    plt.close(fig)


def write_notes(summary: dict) -> None:
    POLICY.mkdir(parents=True, exist_ok=True)
    REFS.mkdir(parents=True, exist_ok=True)
    README.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(SOURCES).to_csv(REFS / "参考文献与来源链接.csv", index=False, encoding="utf-8-sig")

    cn = """# 韩国数字化政策与智能工厂外生冲击识别备忘录

## 结论先行

这不是纯粹的文字背景工作，而是因果识别设计。现有数据可以完成政策叙述与可行性审计，但在获得企业级智能工厂受益名单和实施年份之前，不能把政策变量写成已经验证的工具变量或准自然实验。

## 三类候选政策的判断

1. **制造业创新3.0（2014）**：政策发生在本文2015-2025样本之前，缺少处理前观测，不能直接做样本内的政策前后双重差分。它适合作为韩国制度背景。
2. **韩国数字新政（2020）**：全国同时实施，且与新冠疫情重合，没有清晰的国内未处理组。简单的 `Post2020` 会混合疫情、宏观刺激、报告规则与数字政策，不能被视为外生冲击。
3. **智能工厂政府支持项目（企业分期采用）**：这是最有希望的识别路径。若获得企业名称/事业者登记号、首次实施年份、项目类型和实施等级，可以限制在制造业，采用从未处理或尚未处理企业作为对照，并使用Callaway-Sant'Anna或Sun-Abraham估计。

## 可执行的正式设计

处理变量定义为企业首次完成政府支持智能工厂项目的年份。匹配键优先使用事业者登记号，其次通过企业名称、法人登记信息和DART corp_code建立经人工复核的映射。样本先做重叠审计：上市公司受益企业数、处理前至少三期数据比例、处理年份分布、KOSPI/KOSDAQ构成和行业覆盖。

主模型采用分期处理DiD，报告处理前趋势、动态效应、预期效应窗口、不同建设等级和项目类型的异质性。不可使用传统双向固定效应事件研究作为唯一证据，因为处理时点错开且效应可能异质。标准误按企业聚类，并对政策批次或地区层面的共同冲击进行附加稳健性处理。

## 数据获取路线

优先向韩国中小벤처기업부或KOSMO申请研究用途微观数据；同时利用smart-factory.kr的导入企业支持查询进行抽样核验。现有文献表明，主管部门数据包含2014-2020受支持企业的采用年份、类型、等级与行政区。当前面板没有事业者登记号，因此必须先补充匹配键，不能只凭相似公司名自动合并。

## 当前状态

政策日期、项目规模、识别威胁和推荐估计量已经完成审计。企业级处理名单尚未取得，因此本文件把它列为下一阶段因果扩展，不把它伪装成当前结果。当前论文的实证证据仍是关联性固定效应模型和严格对齐事件研究。
"""
    kr = """# 한국 디지털 정책 및 스마트공장 외생충격 식별 메모

## 핵심 결론

이 작업은 단순한 정책 배경 서술이 아니라 인과식별 설계이다. 현재 자료로 정책 맥락과 식별 가능성은 평가할 수 있지만, 기업별 스마트공장 지원 여부와 도입연도를 확보하기 전에는 정책변수를 검증된 도구변수나 준실험으로 제시할 수 없다.

## 후보 정책별 판단

1. **제조업 혁신 3.0(2014)**: 본 연구의 2015-2025 표본보다 앞서 시행되어 충분한 사전기간이 없다. 따라서 표본 내 단순 정책 전후 DiD에는 적합하지 않으며 제도적 배경으로 사용한다.
2. **한국판 뉴딜·디지털 뉴딜(2020)**: 전국적으로 동시에 시행되었고 코로나19와 시점이 겹친다. 명확한 국내 미처리 집단이 없으므로 단순 `Post2020`은 디지털 정책, 감염병 충격, 거시부양과 공시환경 변화를 분리하지 못한다.
3. **스마트공장 정부지원 사업의 기업별 순차 도입**: 가장 유망한 경로이다. 기업명 또는 사업자등록번호, 최초 도입연도, 사업유형과 구축수준을 확보하면 제조업 표본에서 미처리 또는 아직 처리되지 않은 기업을 대조군으로 하여 Callaway-Sant'Anna 또는 Sun-Abraham 추정량을 적용할 수 있다.

## 권고 실증설계

처리시점은 정부지원 스마트공장 사업의 최초 완료연도로 정의한다. 매칭은 사업자등록번호를 우선하고, 기업명·법인정보·DART corp_code를 이용한 교차검증을 실시한다. 추정 전에 상장기업 수혜기업 수, 처리 전 최소 3개 연도 확보 비율, 처리연도 분포, 시장과 산업별 중첩을 점검한다.

주요 분석은 순차처리 DiD와 동태적 사건연구이며 사전추세, 예상효과, 구축수준과 사업유형별 이질성을 보고한다. 처리시점이 다르고 효과가 이질적일 수 있으므로 전통적 TWFE 사건연구만을 유일한 근거로 사용하지 않는다. 표준오차는 기업 수준에서 군집화하고 정책차수 또는 지역 공통충격도 추가로 점검한다.

## 자료 확보 경로

중소벤처기업부 또는 KOSMO에 연구용 미시자료를 우선 신청하고, smart-factory.kr의 도입기업 지원현황 조회를 표본 검증에 활용한다. 선행연구에 따르면 담당부처 자료에는 2014-2020년 지원기업의 도입연도, 유형, 수준과 행정구역 정보가 포함된다. 현재 패널에는 사업자등록번호가 없으므로 이 매칭키를 먼저 보완해야 하며 유사 기업명만으로 자동 병합해서는 안 된다.

## 현재 상태

정책 시점, 사업규모, 식별위협과 권고 추정량의 검토는 완료되었다. 그러나 기업별 처리목록은 아직 확보하지 못했으므로 이를 후속 인과확장으로 명시하고 현재 결과인 것처럼 제시하지 않는다. 현재 논문의 실증근거는 연관성을 추정하는 고정효과 모형과 공시일 정렬 사건연구이다.
"""
    (POLICY / "01_韩国政策与智能工厂外生冲击识别_中文.md").write_text(cn, encoding="utf-8")
    (POLICY / "02_한국정책과_스마트공장_외생충격_식별_한국어.md").write_text(kr, encoding="utf-8")

    concurrent = summary["concurrent_summary"]
    readme_cn = f"""# 正式版成果包说明

本文件夹是2026-08-16冻结数据和最终模型审计后的正式版本。核心分析面板为{summary['sample']['rows']:,}个公司年度、{summary['sample']['firms']:,}家公司，年份为{summary['sample']['years'][0]}-{summary['sample']['years'][1]}。

建议阅读顺序：先看 `03_中文报告` 或 `04_韩文报告` 的正式实证报告，再看 `02_模型与结果` 的总表和完整系数，最后根据需要读取 `01_核心数据` 与 `06_复现代码`。

并发公告审计覆盖{concurrent.get('query_count', 0):,}个DART日期×市场查询。事件窗定义为年报对应披露交易日至后两个交易日。审计文件保留公告名称、公告类别和是否同日等字段，并给出剔除混杂事件后的CAR结果。

重要解释边界：经营结果未发现稳健统计关联；CAR的负向点估计在单项检验中接近传统显著性阈值，但未通过多重检验，而且未来水平安慰剂失败，因此不能写成已识别的因果惩罚。智能工厂政策设计是下一阶段的潜在因果识别路线，不是当前已经完成的政策冲击估计。
"""
    readme_kr = f"""# 공식 결과 패키지 안내

본 폴더는 2026-08-16 동결자료와 최종 모형 감사를 반영한 공식 버전이다. 핵심 패널은 {summary['sample']['rows']:,}개 기업-연도, {summary['sample']['firms']:,}개 기업, {summary['sample']['years'][0]}-{summary['sample']['years'][1]}년으로 구성된다.

권장 순서는 `04_韩文报告`의 한국어 실증보고서 또는 `03_中文报告`의 중국어 보고서를 먼저 읽고, `02_模型与结果`의 요약표와 전체 계수를 확인한 뒤 필요시 `01_核心数据`와 `06_复现代码`를 이용하는 것이다.

동시공시 감사는 {concurrent.get('query_count', 0):,}개의 DART 날짜×시장 조회를 포함한다. 사건창은 연차보고서 공시거래일부터 이후 두 거래일까지이며, 공시명·분류·동일일 여부와 혼재사건 제외 후 CAR 결과를 제공한다.

해석상 주의: 경영성과에서는 강건한 통계적 연관성이 발견되지 않았다. CAR의 음(-)의 점추정치는 일부 단일 검정에서 전통적 유의수준에 근접하지만 다중검정을 통과하지 못하고 미래수준 위약검정도 실패한다. 따라서 인과적 시장페널티로 표현할 수 없다. 스마트공장 정책설계는 후속 인과식별 경로이며 현재 완료된 정책충격 추정이 아니다.
"""
    (README / "README_中文.md").write_text(readme_cn, encoding="utf-8")
    (README / "README_한국어.md").write_text(readme_kr, encoding="utf-8")
    exclusions = """# 正式推断排除说明

为保证正式包内部一致，本文件夹没有把早期英文年报小样本、测试运行产生的部分并发公告结果、为展示而填写但未由独立编码者真实完成的一致性数值，或显著性导向的试探模型作为正式证据。

正式推断只使用冻结韩文年报面板、严格对齐事件研究数据、完整模型注册表、全量DART并发公告审计和能够由所附代码重现的结果。独立第二编码者验证仍是投稿前必须补做的测量效度步骤。
"""
    (README / "正式推断排除说明.md").write_text(exclusions, encoding="utf-8")


def main() -> int:
    summary = build_summary()
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "formal_inputs.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    save_figures(summary)
    write_notes(summary)
    print(json.dumps({"rows": summary["sample"]["rows"], "firms": summary["sample"]["firms"], "concurrent": summary["concurrent_summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
