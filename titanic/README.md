# Titanic: Machine Learning from Disaster

这是一个从数据审计、特征工程、验证诊断到 Kaggle 提交的二分类项目。最终提交没有使用网络泄漏标签，也没有按 `PassengerId` 硬编码答案。

## 最终成绩

| 指标 | 结果 |
|---|---:|
| Best Public Accuracy | **0.80382** |
| 排名快照 | **460 / 9,682** |
| 排名前百分比 | **Top 4.75%** |
| 最佳提交 | `outputs/submissions/best_submission.csv` |

排名来自 2026-09-11 的公开榜快照，后续可能变化。

## 分析思路

1. 检查缺失、异常值、家庭结构、票号和姓氏群组，避免把年龄和票价的极端值直接删除。
2. 将称谓、家庭规模、母亲/儿童标记、票号群组、姓氏群组、船舱甲板等信息转化为可验证特征。
3. 比较 Logistic Regression、Random Forest、XGBoost、LightGBM、CatBoost 及多模型融合。
4. 使用 OOF、多随机种子、特征消融和群组压力测试，检查随机分层交叉验证是否因家庭成员跨折而过度乐观。
5. 最终采用合法的 woman-child group 规则：只利用训练集标签形成女性与男孩的姓氏/票号群组统计，再对测试集进行推断。

## 一个重要发现

复杂融合模型的随机分层 OOF Accuracy 达到约 `0.86083`，但 Public Accuracy 只有 `0.78229`。群组压力测试约为 `0.78558`，更接近真实榜单。这说明同一家族或同一票号成员被分到训练折和验证折时，会产生乐观验证结果。项目没有继续追逐这个虚高分数，而是调整验证解释，并保留完整实验记录。

## 目录

```text
.
├── data/                 # 数据放置说明，不含 Kaggle 原始数据
├── src/                  # 预处理、特征工程与验证代码
├── notebooks/            # 预建模分析与最终结果演示
├── outputs/figures/      # 描述性分析和模型诊断图
├── outputs/tables/       # 调参、消融、OOF、压力测试和 QA 结果
├── outputs/submissions/  # 最佳提交文件
├── run_all.py            # 主实验流程
├── name_only_submission.py
└── requirements.txt
```

## 运行

```bash
pip install -r requirements.txt
python run_all.py
python name_only_submission.py
```

运行前按 [`data/README.md`](data/README.md) 放置比赛数据。完整复盘见 [`outputs/FINAL_REPORT.md`](outputs/FINAL_REPORT.md)。
