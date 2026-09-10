import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const finalDir = path.join(root, "outputs", "韩国数字化战略论文_正式版_20260816");
const outputPath = path.join(finalDir, "02_模型与结果", "00_正式版数据模型结论总表.xlsx");
const previewDir = path.join(here, "workbook_previews");
const inputs = JSON.parse(await fs.readFile(path.join(here, "formal_inputs.json"), "utf8"));

const wb = Workbook.create();
const colors = {
  navy: "#1F4D78",
  blue: "#2E74B5",
  light: "#EAF1F7",
  pale: "#F4F6F9",
  line: "#D6DEE6",
  text: "#1F2933",
  muted: "#5C6773",
  warning: "#FFF4DE",
  warningText: "#7A4B00",
  negative: "#FDECEC",
  green: "#E9F5EC",
};

function addSheet(name) {
  const sheet = wb.worksheets.add(name);
  sheet.showGridLines = false;
  return sheet;
}

function title(sheet, text, subtitle = "") {
  sheet.mergeCells("A1:H1");
  sheet.getRange("A1").values = [[text]];
  sheet.getRange("A1:H1").format = {
    fill: colors.navy,
    font: { bold: true, color: "#FFFFFF", size: 18, name: "Microsoft YaHei" },
    rowHeight: 32,
    verticalAlignment: "center",
  };
  if (subtitle) {
    sheet.mergeCells("A2:H2");
    sheet.getRange("A2").values = [[subtitle]];
    sheet.getRange("A2:H2").format = {
      fill: colors.light,
      font: { color: colors.muted, size: 10, name: "Microsoft YaHei" },
      rowHeight: 25,
      verticalAlignment: "center",
      wrapText: true,
    };
  }
}

function section(sheet, row, label, endCol = "H") {
  sheet.mergeCells(`A${row}:${endCol}${row}`);
  const range = sheet.getRange(`A${row}:${endCol}${row}`);
  range.values = [[label]];
  range.format = {
    fill: colors.light,
    font: { bold: true, color: colors.navy, size: 12, name: "Microsoft YaHei" },
    rowHeight: 24,
    verticalAlignment: "center",
    borders: { bottom: { style: "thin", color: colors.line } },
  };
}

function writeTable(sheet, startRow, headers, rows, widths = []) {
  const cols = headers.length;
  const endCol = columnName(cols);
  const headerRange = sheet.getRange(`A${startRow}:${endCol}${startRow}`);
  headerRange.values = [headers];
  headerRange.format = {
    fill: colors.navy,
    font: { bold: true, color: "#FFFFFF", size: 10, name: "Microsoft YaHei" },
    wrapText: true,
    verticalAlignment: "center",
    rowHeight: 28,
    borders: { preset: "outside", style: "thin", color: colors.navy },
  };
  if (rows.length) {
    const body = sheet.getRange(`A${startRow + 1}:${endCol}${startRow + rows.length}`);
    body.values = rows;
    body.format = {
      font: { color: colors.text, size: 10, name: "Microsoft YaHei" },
      verticalAlignment: "center",
      wrapText: true,
      borders: {
        insideHorizontal: { style: "thin", color: colors.line },
        bottom: { style: "thin", color: colors.line },
      },
    };
    for (let i = 0; i < rows.length; i += 1) {
      if (i % 2 === 1) sheet.getRange(`A${startRow + 1 + i}:${endCol}${startRow + 1 + i}`).format.fill = colors.pale;
    }
  }
  widths.forEach((width, index) => {
    sheet.getRange(`${columnName(index + 1)}:${columnName(index + 1)}`).format.columnWidth = width;
  });
  return startRow + rows.length;
}

function columnName(n) {
  let x = n;
  let s = "";
  while (x > 0) {
    x -= 1;
    s = String.fromCharCode(65 + (x % 26)) + s;
    x = Math.floor(x / 26);
  }
  return s;
}

function num(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
  return Number(Number(value).toFixed(digits));
}

function labelOutcome(outcome) {
  const labels = {
    SalesGrowth_w_t1: "次年销售增长率",
    ROA_AvgAssets_w_t1: "次年ROA",
    OperatingMargin_w_t1: "次年营业利润率",
    AlignedCAR_0_p2_w: "CAR[0,+2]",
    AlignedMarketAdjustedCAR_0_p2_w: "市场调整CAR[0,+2]",
  };
  return labels[outcome] || outcome;
}

const overview = addSheet("结论总览");
title(overview, "韩国上市公司数字化战略研究：正式结果总览", "冻结日期：2026-08-16 | 用途：论文实证结果审计与写作");
section(overview, 4, "一、冻结样本");
overview.getRange("A5:D8").values = [
  ["公司年度", inputs.sample.rows, "公司数", inputs.sample.firms],
  ["年份", `${inputs.sample.years[0]}-${inputs.sample.years[1]}`, "重复公司年度", inputs.sample.duplicate_firm_years],
  ["数字化指标零值占比", inputs.sample.digital_zero_share, "核心测量", "实质性数字行动句 / 年报总句数"],
  ["事件窗", "披露交易日[0,+2]", "事件日期", "修订后文本的精确披露交易日"],
];
overview.getRange("A5:D8").format = { font: { name: "Microsoft YaHei", size: 10, color: colors.text }, wrapText: true, rowHeight: 25, borders: { preset: "all", style: "thin", color: colors.line } };
overview.getRange("A5:A8").format.fill = colors.pale;
overview.getRange("C5:C8").format.fill = colors.pale;
overview.getRange("B7").format.numberFormat = "0.0%";

section(overview, 10, "二、正式结论");
overview.mergeCells("A11:H13");
overview.getRange("A11").values = [["内部真实效应：公司固定效应与年份固定效应模型未发现数字化战略对次年销售增长、ROA或营业利润率的稳健统计关联。该结果意味着‘年报中披露的实质数字行动’不等于短期可实现的财务回报，而不是证明数字化无效。"]];
overview.getRange("A11:H13").format = { fill: colors.pale, font: { name: "Microsoft YaHei", size: 11, color: colors.text }, wrapText: true, verticalAlignment: "center", rowHeight: 26, borders: { preset: "outside", style: "thin", color: colors.line } };
overview.mergeCells("A15:H17");
overview.getRange("A15").values = [["资本市场反应：首选事件日固定效应与公司/事件日双向聚类模型的点估计为负，但p=0.063且FDR不显著；剔除高相关并发公告后p=0.192，剔除同日其他公告后p=0.523。加上滞后控制较弱和未来水平安慰剂失败，只能写成不稳健的弱负向关联，不能写成市场惩罚。"]];
overview.getRange("A15:H17").format = { fill: colors.warning, font: { name: "Microsoft YaHei", size: 11, color: colors.warningText }, wrapText: true, verticalAlignment: "center", rowHeight: 26, borders: { preset: "outside", style: "thin", color: "#E6C778" } };
overview.mergeCells("A19:H21");
overview.getRange("A19").values = [["因果识别：制造业创新3.0早于样本；2020数字新政与新冠重合且无国内未处理组。最可行扩展是取得智能工厂企业级受益名单及首次实施年份，采用分期处理DiD与现代事件研究。当前文件没有把尚未取得的处理名单包装成结果。"]];
overview.getRange("A19:H21").format = { fill: colors.green, font: { name: "Microsoft YaHei", size: 11, color: colors.text }, wrapText: true, verticalAlignment: "center", rowHeight: 26, borders: { preset: "outside", style: "thin", color: "#9BC7A6" } };
section(overview, 23, "三、首选模型关键数值");
overview.getRange("A24:F24").values = [["路径", "因变量", "系数", "标准误", "p值", "结论"]];
overview.getRange("A24:F24").format = { fill: colors.navy, font: { bold: true, color: "#FFFFFF", name: "Microsoft YaHei", size: 10 }, rowHeight: 25 };
const opCore = inputs.operating_core;
const preferredCar = inputs.car_core.find((x) => x.model_id === "CAR_EVENT_DATE_FE_TWO_WAY");
const coreRows = opCore.map((x) => ["内部经营", labelOutcome(x.outcome), num(x.coefficient, 6), num(x.std_error, 6), num(x.p_value, 4), "不显著"]);
coreRows.push(["资本市场", "CAR[0,+2]", num(preferredCar.coefficient, 6), num(preferredCar.std_error, 6), num(preferredCar.p_value, 4), "弱负向，未通过FDR"]);
overview.getRange(`A25:F${24 + coreRows.length}`).values = coreRows;
overview.getRange(`A25:F${24 + coreRows.length}`).format = { font: { name: "Microsoft YaHei", size: 10, color: colors.text }, borders: { preset: "all", style: "thin", color: colors.line }, rowHeight: 23 };
overview.getRange(`C25:E${24 + coreRows.length}`).format.numberFormat = "0.0000";
overview.freezePanes.freezeRows(2);
overview.getRange("A:H").format.columnWidth = 16;

const sample = addSheet("样本与测量");
title(sample, "样本与数字化战略测量", "句子级语义筛选，不使用简单关键词词频");
section(sample, 4, "样本统计");
writeTable(sample, 5, ["指标", "数值", "解释"], [
  ["公司年度", inputs.sample.rows, "冻结分析面板"],
  ["公司数", inputs.sample.firms, "DART corp_code去重"],
  ["年份", `${inputs.sample.years[0]}-${inputs.sample.years[1]}`, "财年"],
  ["DigitalStrategy均值", inputs.sample.digital_mean, "实质行动句占总句数"],
  ["DigitalStrategy标准差", inputs.sample.digital_std, "公司年度分布"],
  ["零值占比", inputs.sample.digital_zero_share, "大量年报未识别到实质数字行动句"],
  ["P90", inputs.sample.digital_p90, "分布偏斜，故补做两部分模型与经验logit"],
], [24, 18, 66]);
sample.getRange("B9:B11").format.numberFormat = "0.0000";
sample.getRange("B10").format.numberFormat = "0.0%";
section(sample, 14, "年度覆盖与数字披露");
const yearRows = inputs.sample.year_counts.map((x) => [x.year, x.observations, x.firms, x.digital_mean, x.positive_digital_share]);
writeTable(sample, 15, ["年份", "公司年度", "公司数", "DigitalStrategy均值", "正值占比"], yearRows, [12, 15, 15, 22, 18]);
sample.getRange(`D16:E${15 + yearRows.length}`).format.numberFormat = "0.00%";
section(sample, 29, "测量定义");
writeTable(sample, 30, ["变量", "定义", "正式用途"], [
  ["DigitalStrategy", "实质性数字战略行动句数 / 去重总句数", "主解释变量；进入回归前标准化"],
  ["BMI_Reconstruction", "商业模式重构类数字句数 / 总句数", "内部路径；与运营数字化分解使用"],
  ["PureSignal", "max(市场可见数字句数-实质行动句数,0) / 总句数", "替代原MarketSignalDisclosure，避免与主变量机械重合"],
  ["RelativeDigitalSignal", "DigitalStrategy减行业×年份均值；小组不足5时退回年份均值", "控制共同年度数字化词汇上升"],
  ["Boilerplate", "口号式数字句数 / 总句数", "测量有效性与市场反应诊断"],
], [24, 62, 42]);
sample.freezePanes.freezeRows(2);

const models = addSheet("最终模型");
title(models, "最终模型设定", "确认性模型与探索性检验分开报告");
section(models, 4, "内部经营路径");
writeTable(models, 5, ["要素", "正式设定"], [
  ["因变量", "次年销售增长率、次年ROA、次年营业利润率；1%/99%缩尾"],
  ["解释变量", "标准化DigitalStrategy"],
  ["固定效应", "公司固定效应 + 财年固定效应"],
  ["标准误", "按公司聚类"],
  ["核心控制", "规模、杠杆、同期ROA、销售增长、流动性、营业利润率、公司年龄、亏损、负净资产、年报篇幅"],
  ["扩展控制", "资产周转、营运资本、员工、最大股东持股；2020+另检验研发强度与外部董事比例"],
], [26, 102]);
section(models, 14, "资本市场路径");
writeTable(models, 15, ["要素", "正式设定"], [
  ["因变量", "严格对齐的CAR[0,+2]，报告披露交易日至后两个交易日；1%/99%缩尾"],
  ["解释变量", "标准化DigitalStrategy"],
  ["固定效应", "公司固定效应 + 精确披露交易日固定效应"],
  ["标准误", "公司与披露交易日双向聚类"],
  ["控制", "经营模型核心控制 + 财年股票收益 + 财年日收益波动率"],
  ["首选原因", "吸收同一天全市场冲击，并允许公司内和事件日内误差相关"],
], [26, 102]);
section(models, 24, "探索与约束");
writeTable(models, 25, ["项目", "处理原则"], [
  ["非线性", "平方项、正值样本三次项、四分位组与两部分模型仅作探索；联合检验不支持稳定曲线"],
  ["机制", "Digital×BMI、Digital×信号及成分分解不作为已识别中介效应"],
  ["多重检验", "同一模型家族使用Benjamini-Hochberg FDR校正"],
  ["因果语言", "安慰剂失败且无外生处理，因此使用关联性表述"],
], [26, 102]);
models.freezePanes.freezeRows(2);

const operating = addSheet("经营绩效结果");
title(operating, "经营绩效：确认性结果", "公司与年份固定效应；标准误按公司聚类");
const opRows = inputs.operating_core.map((x) => [labelOutcome(x.outcome), x.focal, num(x.coefficient, 6), num(x.std_error, 6), num(x.p_value, 4), num(x.fdr_within_family, 4), x.n, x.firms, num(x.r_squared_within, 4), "不支持短期经营效应"]);
writeTable(operating, 4, ["因变量", "核心项", "系数", "标准误", "p值", "FDR", "N", "公司数", "Within R²", "解释"], opRows, [23, 18, 14, 14, 11, 11, 14, 14, 15, 36]);
operating.getRange(`C5:F${4 + opRows.length}`).format.numberFormat = "0.0000";
operating.mergeCells("A10:J13");
operating.getRange("A10").values = [["正式解释：三项确认性因变量均未达到传统显著性水平，完整83个经营模型也没有原始p<0.05或FDR<0.05的数字化核心系数。经验logit、变化量、三年持续强度、两部分模型、行业×年份固定效应、Driscoll-Kraay、扩展控制、剔除退市公司、一阶差分和公司趋势处理均未形成一致证据。"]];
operating.getRange("A10:J13").format = { fill: colors.pale, font: { name: "Microsoft YaHei", size: 11, color: colors.text }, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: colors.line } };

const carSheet = addSheet("资本市场结果");
title(carSheet, "资本市场反应：事件研究结果", "严格对齐披露交易日；CAR[0,+2]");
const carRows = inputs.car_core.map((x) => [x.model_id, x.description, num(x.coefficient, 6), num(x.std_error, 6), num(x.p_value, 4), num(x.fdr_within_family, 4), x.n, x.firms, x.effect_spec, x.covariance]);
writeTable(carSheet, 4, ["模型", "设定", "系数", "标准误", "p值", "FDR", "N", "公司数", "固定效应", "协方差"], carRows, [31, 51, 13, 13, 11, 11, 14, 14, 22, 22]);
carSheet.getRange(`C5:F${4 + carRows.length}`).format.numberFormat = "0.0000";
const carEnd = 4 + carRows.length;
section(carSheet, carEnd + 3, "解释边界", "J");
carSheet.mergeCells(`A${carEnd + 4}:J${carEnd + 7}`);
carSheet.getRange(`A${carEnd + 4}`).values = [["事件日双向聚类的首选系数约为-0.00269，意味着DigitalStrategy提高1个标准差与三日CAR低约0.269个百分点相关。但p=0.063、FDR=0.129，滞后控制模型p=0.222，且未来数字化水平安慰剂p=0.0035。方向可以讨论为投资者对实施成本、兑现风险或信息复杂性的短期折价，但证据不足以支持确定性或因果性结论。"]];
carSheet.getRange(`A${carEnd + 4}:J${carEnd + 7}`).format = { fill: colors.warning, font: { name: "Microsoft YaHei", size: 11, color: colors.warningText }, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#E6C778" } };

const concurrent = addSheet("并发公告审计");
title(concurrent, "事件窗并发公告审计", "DART历史公告页：KOSPI与KOSDAQ逐日逐页覆盖");
const cs = inputs.concurrent_summary;
writeTable(concurrent, 4, ["指标", "数值", "定义"], [
  ["事件数", cs.event_rows, "存在精确披露交易日的公司年度"],
  ["日期×市场查询", cs.query_count, "每个日期分别覆盖KOSPI和KOSDAQ"],
  ["目标年报收件号覆盖率", cs.focal_annual_report_receipt_coverage, "审计页观察到目标rcept_no的比例"],
  ["存在任何并发公告", cs.events_with_any_concurrent, "目标年报之外的事件窗内公告"],
  ["任何并发公告占比", cs.share_with_any_concurrent, "事件级比例"],
  ["高相关并发公告占比", cs.share_with_high_relevance, "业绩、融资、治理、审计、诉讼、公平披露等"],
  ["同日并发公告占比", cs.share_with_same_day, "年报披露交易日同日"],
], [30, 22, 76]);
concurrent.getRange("B5:B6").format.numberFormat = "#,##0";
concurrent.getRange("B8").format.numberFormat = "#,##0";
concurrent.getRange("B7").format.numberFormat = "0.00%";
concurrent.getRange("B9:B11").format.numberFormat = "0.00%";
section(concurrent, 14, "剔除并发公告后的CAR", "J");
const ccRows = inputs.concurrent_models.map((x) => [x.model_id, x.description, num(x.coefficient, 6), num(x.std_error, 6), num(x.p_value, 4), num(x.fdr_concurrent_family, 4), x.n, x.firms, x.effect_spec, x.covariance]);
writeTable(concurrent, 15, ["模型", "样本", "系数", "标准误", "p值", "审计族FDR", "N", "公司数", "固定效应", "聚类"], ccRows, [34, 42, 13, 13, 11, 15, 14, 14, 21, 21]);
concurrent.getRange(`C16:F${15 + ccRows.length}`).format.numberFormat = "0.0000";
concurrent.freezePanes.freezeRows(2);

const robust = addSheet("稳健性诊断");
title(robust, "稳健性与诊断结果", "时间边界、替代构造、非线性、市场异质性与安慰剂");
section(robust, 4, "文本修订时间边界", "I");
const temporalRows = inputs.temporal_tests.map((x) => [x.description, labelOutcome(x.outcome), num(x.coefficient, 6), num(x.std_error, 6), num(x.p_value, 4), x.n, x.firms, x.effect_spec, x.covariance]);
writeTable(robust, 5, ["样本限制", "因变量", "系数", "标准误", "p值", "N", "公司数", "固定效应", "聚类"], temporalRows, [30, 26, 13, 13, 11, 14, 14, 22, 20]);
robust.getRange(`C6:E${5 + temporalRows.length}`).format.numberFormat = "0.0000";
const rStart = 8 + temporalRows.length;
section(robust, rStart, "资本市场关键诊断", "I");
const diagnosticRows = inputs.car_diagnostics.map((x) => [x.model_id, x.focal, num(x.coefficient, 6), num(x.std_error, 6), num(x.p_value, 4), num(x.fdr_within_family, 4), x.n, x.description, x.sample_note]);
writeTable(robust, rStart + 1, ["模型", "变量", "系数", "标准误", "p值", "FDR", "N", "说明", "样本"], diagnosticRows, [35, 27, 13, 13, 11, 11, 14, 47, 30]);
robust.getRange(`C${rStart + 2}:F${rStart + 1 + diagnosticRows.length}`).format.numberFormat = "0.0000";
robust.freezePanes.freezeRows(2);

const policy = addSheet("政策识别");
title(policy, "韩国政策冲击与因果识别判断", "正式结论：完成可行性审计，尚未取得企业级处理名单");
writeTable(policy, 4, ["候选冲击", "可用性", "主要威胁", "正式用途"], [
  ["制造业创新3.0（2014）", "不适合样本内前后DiD", "政策早于2015样本，缺少处理前期", "制度背景"],
  ["数字新政（2020）", "不适合简单Post2020", "全国实施、无国内未处理组、与COVID重合", "背景与异质暴露扩展"],
  ["智能工厂企业分期采用", "最有希望", "需企业级受益名单、处理年份和可靠匹配键", "Callaway-Sant'Anna / Sun-Abraham分期处理DiD"],
], [31, 31, 49, 49]);
section(policy, 10, "执行要求");
writeTable(policy, 11, ["步骤", "要求"], [
  ["1. 数据", "向中小벤처기업부/KOSMO申请微观数据，补充事业者登记号，保留首次采用年份、类型、等级、地区"],
  ["2. 重叠", "先报告上市制造业样本中受益企业数量、处理年份分布、处理前三期覆盖和行业/市场重叠"],
  ["3. 估计", "使用从未处理或尚未处理企业，报告组别-时间ATT、动态效应和处理前趋势"],
  ["4. 稳健性", "处理预期、不同项目等级、政策批次/地区聚类、匹配误差和COVID敏感性"],
  ["5. 边界", "取得并匹配企业级名单前，不声称已完成外生冲击或工具变量识别"],
], [22, 138]);
section(policy, 20, "来源链接");
const sourceRows = inputs.sources.map((x) => [x.year, x.type, x.title, x.organization, x.use, x.url]);
writeTable(policy, 21, ["年份", "类型", "标题", "机构/期刊", "用途", "URL"], sourceRows, [12, 27, 48, 40, 75, 85]);
policy.freezePanes.freezeRows(2);

const index = addSheet("文件索引");
title(index, "正式成果包文件索引", "数据、结果、报告、政策资料与复现代码");
const files = [];
async function walk(dir) {
  for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(full);
    else if (!entry.name.endsWith(".inspect.ndjson") && !full.includes("workbook_previews")) {
      const stat = await fs.stat(full);
      files.push([path.relative(finalDir, full), stat.size, entry.name.split(".").pop().toLowerCase(), "正式包内文件"]);
    }
  }
}
await walk(finalDir);
files.sort((a, b) => a[0].localeCompare(b[0], "zh-CN"));
writeTable(index, 4, ["相对路径", "字节", "类型", "说明"], files, [92, 18, 14, 36]);
index.getRange(`B5:B${4 + files.length}`).format.numberFormat = "#,##0";
index.freezePanes.freezeRows(4);

for (let i = 0; i < wb.worksheets.items.length; i += 1) {
  const sheet = wb.worksheets.getItemAt(i);
  const used = sheet.getUsedRange();
  if (used) used.format.font.name = "Microsoft YaHei";
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const out = await SpreadsheetFile.exportXlsx(wb);
await out.save(outputPath);

await fs.mkdir(previewDir, { recursive: true });
for (const name of ["结论总览", "样本与测量", "最终模型", "经营绩效结果", "资本市场结果", "并发公告审计", "稳健性诊断", "政策识别", "文件索引"]) {
  const rendered = await wb.render({ sheetName: name, autoCrop: "all", scale: 1 });
  await fs.writeFile(path.join(previewDir, `${name}.png`), new Uint8Array(await rendered.arrayBuffer()));
}

const inspect = await wb.inspect({ kind: "sheet,table", maxChars: 6000, tableMaxRows: 12, tableMaxCols: 12, tableMaxCellChars: 100 });
await fs.writeFile(path.join(here, "formal_workbook.inspect.ndjson"), inspect.ndjson, "utf8");
const errors = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, summary: "final formula error scan" });
await fs.writeFile(path.join(here, "formal_workbook_errors.inspect.ndjson"), errors.ndjson, "utf8");
console.log(JSON.stringify({ outputPath, sheets: wb.worksheets.items.length, filesIndexed: files.length }, null, 2));
