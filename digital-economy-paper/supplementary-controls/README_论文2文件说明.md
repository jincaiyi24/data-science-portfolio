# 论文2文件说明

本文件夹用于保存“新增控制变量与模型增强”结果。本次处理不包含人工句子验证，不补造缺失数据，所有新增财务变量均来自 OpenDART 或既有冻结面板。

## 一、优先查看的文件

1. `论文2_新增控制变量与模型增强结果.xlsx`
   - 汇总 Excel，包含核心系数、完整回归、新增控制变量缺失率、市场年份覆盖率、变量定义、OpenDART 科目明细、Python 与 Stata 复核。

2. `04_说明文档/论文2_新增控制变量与模型增强报告.docx`
   - 可直接阅读的正式说明报告，已经渲染检查。

3. `04_说明文档/_render_check_final3/`
   - Word 渲染检查图片和 PDF，只用于检查排版。

4. `03_复现代码/paper2_extended_controls_pipeline.py`
   - 从新增控制变量抓取、变量构造、模型估计到 Stata 复核数据导出的完整 Python 代码。

5. `05_Stata复核/paper2_stata_validation.do`
   - Stata 18 复核代码。

## 二、本次新增数据

新增 OpenDART 科目来自单一公司全部财务报表接口 `fnlttSinglAcntAll`，年度报告代码为 `11011`。变量只在财务报表中能识别对应科目时取值，不把缺失值填为 0。

新增控制变量包括：

- OpenDART 研发强度：`RAndDExpense / abs(Sales)`
- 无形资产比率：`IntangibleAssets / TotalAssets`
- 固定资产比率：`PPE / TotalAssets`
- 经营现金流比率：`OperatingCashFlow / TotalAssets`
- 资本开支强度：`abs(CAPEX) / TotalAssets`
- 文本研发比例：来自既有面板中的研发相关披露口径

## 三、核心结论

主结果没有被新增高覆盖控制变量推翻。基准模型中，BMI 披露的系数为 `0.030243`，p 值小于 `0.001`。加入无形资产比率、固定资产比率、经营现金流比率和资本开支强度后，系数为 `0.029818`，p 值仍小于 `0.001`，样本量为 `12,658`。

OpenDART 研发强度覆盖率只有约 `4.0%`，进入全扩展模型后样本只剩 `480` 个公司年度，因此不适合作为主模型控制变量。该结果应解释为“研发费用科目覆盖不足导致样本选择变化”，不能解释为主结果被研发投入否定。

同时控制非 BMI 数字披露后，BMI 披露仍显著，非 BMI 数字披露不显著。这支持论文核心区分：不是所有数字披露都与未来经营效率相关，更关键的是商业模式导向的数字披露。

## 四、复核结果

Python 与 Stata 对核心模型的系数和样本量一致，标准误仅存在极小实现差异，不改变统计判断。复核结果见：

- `02_模型结果/04_Python与Stata核心模型复核对照.csv`
- `05_Stata复核/paper2_stata_validation.log`

## 五、来源链接

- OpenDART fnlttSinglAcntAll 官方接口说明：https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020
- Benjamini and Hochberg (1995)：https://academic.oup.com/jrsssb/article/57/1/289/7035855
- Benjamini and Yekutieli (2001)：https://projecteuclid.org/journals/annals-of-statistics/volume-29/issue-4/The-control-of-the-false-discovery-rate-in-multiple-testing/10.1214/aos/1013699998.short
