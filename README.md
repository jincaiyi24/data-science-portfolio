# Data Science Portfolio

这个仓库整理了四个完整的数据分析项目，覆盖回归、分类、客户倾向分析和企业面板数据实证研究。项目保留了问题定义、数据审计、模型比较、验证诊断和结果解释，重点不是堆叠算法，而是说明每一步选择的依据与局限。

## Projects

| 项目 | 问题类型 | 主要方法 | 结果 |
|---|---|---|---|
| [House Prices](house-prices/README.md) | 回归 | Elastic Net、Gradient Boosting、XGBoost、RBF-SVR 与 OOF 融合 | Kaggle Public RMSE **0.12163**；排名快照 **430 / 3,454** |
| [Titanic](titanic/README.md) | 二分类 | 特征工程、树模型、Boosting、多种子交叉验证、规则模型 | Kaggle Public Accuracy **0.80382**；排名快照 **460 / 9,682** |
| [EV Purchase Propensity & Customer Analytics](ev-purchase-customer-analytics/README.md) | 二分类与客户分析 | XGBoost、OOF 融合、业务分群、MySQL 四表分析链路 | OOF ROC-AUC **0.945713**；Kaggle Public AUC **0.94589**；MySQL 13/13 校验通过 |
| [Digital Economy Paper](digital-economy-paper/README.md) | 企业面板与文本分析 | 韩文年报句子分类、公司/年份固定效应、聚类标准误、稳健性与边界检验 | 22,654 个公司年度的基础面板；主回归 13,980 个公司年度 |

> Kaggle 排名是提交时的快照，会随参赛人数变化。论文结果属于条件相关性证据，不作因果解释。

## 我在项目中重点处理的问题

- 区分结构性缺失与真正未知，避免机械填补破坏变量含义。
- 把预处理放入交叉验证流程，降低数据泄漏风险。
- 使用 OOF 和多种子验证比较模型，并检查本地验证与公开榜分数的偏差。
- 用消融实验、残差分析、分布检查和群组压力测试解释模型为什么有效、哪里不可靠。
- 将真实 OOF/Test 预测、客户特征、既有业务分群和模型指标装入 MySQL，通过主外键、窗口查询和 Python-SQL 对账形成可审计分析链路。
- 在论文项目中同时报告支持性和非支持性结果，明确多重检验、模型选择和非因果边界。

## 数据说明

仓库不包含 Kaggle 比赛原始数据、DART/OpenDART 原始年报全文、大型企业面板和第三方市场数据。这样做是为了遵守数据来源条款、避免公开不必要的公司明细，并控制仓库体积。每个子项目都提供数据来源、目录要求或变量字典。

## 阅读顺序

1. 先读各项目的 `README.md`。
2. 查看报告和关键图表，理解问题、验证设计与结论。
3. 再进入 `src/`、`notebooks/` 和 `results/` 检查实现及证据。

## Environment

两个 Kaggle 项目建议使用 Python 3.11 或 3.12。依赖分别记录在各子项目的 `requirements.txt` 中。数字经济论文同时包含 Python 和 Stata 复核材料。

## 使用说明

本仓库用于个人学习、求职展示和方法复盘。论文文本、图表和研究设计保留作者权利；引用或复用前请先说明来源。
