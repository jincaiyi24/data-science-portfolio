# Titanic 生存预测竞赛报告

## 最终结果

- Kaggle 账号：`kimzaiyi1`
- 最佳提交：`submission_10_name_wcg_exact.csv`
- Public Accuracy：**0.80382**
- 当前排名：**460 / 9682**（约前 4.75%）
- 今日提交：10 次，均已完成评分

## 方法

项目从性别规则、逻辑回归和随机森林基线开始，逐步加入称谓、家庭规模、票号、票价、客舱、年龄分组、交互项和同行组生还信息。共比较 10 类模型，并对 CatBoost、RandomForest、LightGBM、XGBoost 各完成 50 次 Optuna 搜索，再用 5 个随机种子的分层五折验证检查稳定性。

本地最佳加权融合 OOF Accuracy 为 0.86083。最佳单模型为 CatBoost，平均 CV 为 0.84758 ± 0.02443。但按家庭和票号整体隔离的压力测试只有 0.78558，说明普通随机折高估了同行特征的泛化能力。实际榜单也证实复杂融合只有 0.78229，不能用漂亮的 OOF 数字代替真实泛化判断。

消融中产生正增量的阶段包括：E1_Title（+0.0168）、E2_Family（+0.0056）、E5_Cabin（+0.0090）、E8_FamilySurvival（+0.0090）、E9_TicketSurvival（+0.0079）。其中 Title 与家庭结构最稳定；直接加入大量票号和交互项对线性模型反而有损失，说明特征数量不是越多越好。

## 最佳提交的逻辑

最终最佳方案不是最复杂的模型，而是精确的 woman-child group 规则：

1. 从姓名提取成年男性、女性和 `Master` 男童。
2. 成年男性不参与姓氏同行组的建立。
3. 女性和男童优先按姓氏成组；无法成组时，使用共同票号恢复其同行姓氏。
4. 女性默认生还，但若已知同行女性/男童全部遇难，则改判遇难。
5. 男童默认遇难，只有已知同行女性/男童全部生还时才改判生还。

该规则只使用官方 train/test 中的姓名、性别、称谓、票号以及 train 标签，没有使用外部测试答案。它只改变性别基线的 18 个预测，却将榜单成绩提高到 0.80382。

## 失败与改进

最初的目标生还率特征虽然严格在折外计算，但随机 CV 会让同一家庭或票号同时落入训练折与验证折，因此 OOF 高达 0.86，却没有转化为榜单成绩。真正有效的改进不是继续增加模型，而是：

- 增加 group-aware 压力测试，识别验证虚高。
- 把弱的平滑同行证据改成少量、明确的全生或全亡规则。
- 用榜单反馈只做候选方案选择，不反推或硬编码单个 PassengerId 的答案。

若下一提交周期继续冲分，应先在当前姓名组规则上研究“单身乘客模型”，并坚持独立 OOF；不要通过公开历史名单获取测试标签。

## 复现与文件

- `run_all.py`：完整模型、消融、调参、融合与输出流程
- `name_only_submission.py`：最佳提交的最小复现脚本
- `outputs/tables/experiment_results.csv`：实验总表
- `outputs/tables/kaggle_submission_history.csv`：真实提交历史
- `outputs/tables/kaggle_rank_snapshot.csv`：排名快照
- `outputs/submissions/submission_10_name_wcg_exact.csv`：最佳提交文件
- `notebooks/final_competition_results.ipynb`：已执行结果 Notebook

BEST SINGLE MODEL:
CatBoost

BEST LOCAL OOF:
0.86083（注意随机分组乐观偏差）

BEST KAGGLE SUBMISSION:
outputs/submissions/submission_10_name_wcg_exact.csv

BEST KAGGLE PUBLIC ACCURACY:
0.80382

CURRENT RANK:
460 / 9682
