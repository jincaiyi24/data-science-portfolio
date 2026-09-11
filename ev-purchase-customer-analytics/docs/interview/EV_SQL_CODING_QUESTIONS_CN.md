# EV SQL Coding Questions

共 30 题，覆盖 Easy / Medium / Hard。

## 1. [Easy] 统计训练和测试行数

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“统计训练和测试行数”的明细或聚合结果。

```sql
SELECT source_set, COUNT(*) AS customers FROM ev_customer_features GROUP BY source_set;
```

**解题逻辑：** 按 source_set 聚合。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 2. [Easy] 检查重复客户 id

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“检查重复客户 id”的明细或聚合结果。

```sql
SELECT id, COUNT(*) AS n FROM ev_customer_features GROUP BY id HAVING COUNT(*) > 1;
```

**解题逻辑：** HAVING 过滤聚合结果。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 3. [Easy] 找出概率越界记录

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“找出概率越界记录”的明细或聚合结果。

```sql
SELECT * FROM ev_model_predictions WHERE predicted_probability NOT BETWEEN 0 AND 1;
```

**解题逻辑：** 用业务域约束筛查。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 4. [Easy] 计算训练集购买意向率

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“计算训练集购买意向率”的明细或聚合结果。

```sql
SELECT AVG(will_buy_ev='Yes') AS rate FROM ev_customer_features WHERE source_set='train';
```

**解题逻辑：** 布尔均值等于比例。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 5. [Easy] 按城市统计客户数

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“按城市统计客户数”的明细或聚合结果。

```sql
SELECT city_type, COUNT(*) customers FROM ev_customer_features GROUP BY city_type ORDER BY customers DESC;
```

**解题逻辑：** 基本分组排序。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 6. [Easy] 统计有家庭充电的占比

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“统计有家庭充电的占比”的明细或聚合结果。

```sql
SELECT AVG(home_charging_possible='Yes') AS share FROM ev_customer_features;
```

**解题逻辑：** 明确总体分母。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 7. [Easy] 查看最高概率的 20 名测试客户

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“查看最高概率的 20 名测试客户”的明细或聚合结果。

```sql
SELECT id, predicted_probability FROM ev_model_predictions WHERE source_set='test' ORDER BY predicted_probability DESC LIMIT 20;
```

**解题逻辑：** 过滤后降序取 Top N。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 8. [Easy] 列出全部客户分群

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“列出全部客户分群”的明细或聚合结果。

```sql
SELECT customer_segment, COUNT(*) customers FROM ev_customer_segments GROUP BY customer_segment;
```

**解题逻辑：** 检查分群分布。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 9. [Easy] 找出缺失训练标签

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“找出缺失训练标签”的明细或聚合结果。

```sql
SELECT id FROM ev_customer_features WHERE source_set='train' AND will_buy_ev IS NULL;
```

**解题逻辑：** 集合条件与 NULL 判断。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 10. [Easy] 查询最优 AUC 记录

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“查询最优 AUC 记录”的明细或聚合结果。

```sql
SELECT model_name, model_version, roc_auc FROM ev_model_metrics WHERE roc_auc IS NOT NULL ORDER BY roc_auc DESC LIMIT 1;
```

**解题逻辑：** 过滤 NULL 后排序。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 11. [Medium] 检查预测连接覆盖率

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“检查预测连接覆盖率”的明细或聚合结果。

```sql
SELECT COUNT(p.id)/COUNT(*) coverage FROM ev_customer_features f LEFT JOIN ev_model_predictions p ON p.id=f.id;
```

**解题逻辑：** LEFT JOIN 保留分母。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 12. [Medium] 比较补贴组购买率

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“比较补贴组购买率”的明细或聚合结果。

```sql
SELECT subsidy_available, COUNT(*) n, AVG(will_buy_ev='Yes') rate FROM ev_customer_features WHERE source_set='train' GROUP BY subsidy_available;
```

**解题逻辑：** 仅使用有标签集合。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 13. [Medium] 计算各分群相对总体提升

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“计算各分群相对总体提升”的明细或聚合结果。

```sql
WITH b AS (SELECT AVG(will_buy_ev='Yes') r FROM ev_customer_features WHERE source_set='train') SELECT s.customer_segment, AVG(f.will_buy_ev='Yes')-b.r lift FROM ev_customer_segments s JOIN ev_customer_features f ON f.id=s.id CROSS JOIN b WHERE f.source_set='train' GROUP BY s.customer_segment,b.r;
```

**解题逻辑：** CTE 保存总体基线。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 14. [Medium] 按城市给分群倾向排序

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“按城市给分群倾向排序”的明细或聚合结果。

```sql
WITH x AS (SELECT f.city_type,s.customer_segment,AVG(p.predicted_probability) score FROM ev_customer_features f JOIN ev_customer_segments s ON s.id=f.id JOIN ev_model_predictions p ON p.id=f.id GROUP BY f.city_type,s.customer_segment) SELECT *,DENSE_RANK() OVER(PARTITION BY city_type ORDER BY score DESC) rnk FROM x;
```

**解题逻辑：** 先聚合再开窗。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 15. [Medium] 计算每个十分位的实际正例率

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“计算每个十分位的实际正例率”的明细或聚合结果。

```sql
SELECT p.prediction_decile,COUNT(*) n,AVG(p.actual_target) actual_rate FROM ev_model_predictions p WHERE p.source_set='train' GROUP BY p.prediction_decile ORDER BY p.prediction_decile;
```

**解题逻辑：** actual_target 为 0/1。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 16. [Medium] 找高倾向但充电受限客户

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“找高倾向但充电受限客户”的明细或聚合结果。

```sql
SELECT f.id,p.predicted_probability FROM ev_customer_features f JOIN ev_model_predictions p ON p.id=f.id WHERE p.prediction_decile<=2 AND f.home_charging_possible='No' AND f.charging_stations_near_home+f.charging_stations_near_work<=3;
```

**解题逻辑：** 连接特征与预测并组合条件。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 17. [Medium] 统计分群在各城市的占比

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“统计分群在各城市的占比”的明细或聚合结果。

```sql
WITH x AS (SELECT f.city_type,s.customer_segment,COUNT(*) n FROM ev_customer_features f JOIN ev_customer_segments s ON s.id=f.id GROUP BY f.city_type,s.customer_segment) SELECT *,n/SUM(n) OVER(PARTITION BY city_type) share FROM x;
```

**解题逻辑：** 窗口总和保留分群行。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 18. [Medium] 找第二高倾向分群

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“找第二高倾向分群”的明细或聚合结果。

```sql
WITH x AS (SELECT customer_segment,AVG(segmentation_score) score,DENSE_RANK() OVER(ORDER BY AVG(segmentation_score) DESC) rnk FROM ev_customer_segments GROUP BY customer_segment) SELECT * FROM x WHERE rnk=2;
```

**解题逻辑：** DENSE_RANK 处理并列。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 19. [Medium] 比较每个模型不同折的稳定性

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“比较每个模型不同折的稳定性”的明细或聚合结果。

```sql
SELECT model_name,AVG(roc_auc) mean_auc,STDDEV_POP(roc_auc) std_auc,MIN(roc_auc) min_auc,MAX(roc_auc) max_auc FROM ev_model_metrics WHERE fold IS NOT NULL GROUP BY model_name;
```

**解题逻辑：** 逐折记录聚合。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 20. [Medium] 识别 source_set 不一致

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“识别 source_set 不一致”的明细或聚合结果。

```sql
SELECT f.id FROM ev_customer_features f JOIN ev_model_predictions p ON p.id=f.id JOIN ev_customer_segments s ON s.id=f.id WHERE f.source_set<>p.source_set OR f.source_set<>s.source_set;
```

**解题逻辑：** 连接后核对冗余标签。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 21. [Hard] 计算累积 Top-k 客户覆盖的正例占比

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“计算累积 Top-k 客户覆盖的正例占比”的明细或聚合结果。

```sql
WITH r AS (SELECT actual_target,ROW_NUMBER() OVER(ORDER BY predicted_probability DESC) rn,COUNT(*) OVER() n,SUM(actual_target) OVER() positives FROM ev_model_predictions WHERE source_set='train'), c AS (SELECT rn,n,SUM(actual_target) OVER(ORDER BY rn) cum_pos,positives FROM r) SELECT rn/n population_share,cum_pos/positives positive_coverage FROM c WHERE rn IN (66867,133733,200600);
```

**解题逻辑：** 排序后做累计正例覆盖。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 22. [Hard] 计算十分位 lift

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“计算十分位 lift”的明细或聚合结果。

```sql
WITH d AS (SELECT prediction_decile,AVG(actual_target) rate FROM ev_model_predictions WHERE source_set='train' GROUP BY prediction_decile), b AS (SELECT AVG(actual_target) rate FROM ev_model_predictions WHERE source_set='train') SELECT d.prediction_decile,d.rate,d.rate/b.rate lift FROM d CROSS JOIN b;
```

**解题逻辑：** 以总体正例率为基准。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 23. [Hard] 比较相邻十分位分数差

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“比较相邻十分位分数差”的明细或聚合结果。

```sql
WITH d AS (SELECT prediction_decile,AVG(predicted_probability) score FROM ev_model_predictions WHERE source_set='test' GROUP BY prediction_decile) SELECT *,score-LAG(score) OVER(ORDER BY prediction_decile) gap FROM d;
```

**解题逻辑：** LAG 获取上一行。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 24. [Hard] 每个城市取前 100 名客户

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“每个城市取前 100 名客户”的明细或聚合结果。

```sql
WITH r AS (SELECT f.id,f.city_type,p.predicted_probability,ROW_NUMBER() OVER(PARTITION BY f.city_type ORDER BY p.predicted_probability DESC) rn FROM ev_customer_features f JOIN ev_model_predictions p ON p.id=f.id WHERE f.source_set='test') SELECT * FROM r WHERE rn<=100;
```

**解题逻辑：** 分区排名实现 group Top N。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 25. [Hard] 构建模型校准误差摘要

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“构建模型校准误差摘要”的明细或聚合结果。

```sql
WITH d AS (SELECT prediction_decile,AVG(predicted_probability) pred,AVG(actual_target) actual,COUNT(*) n FROM ev_model_predictions WHERE source_set='train' GROUP BY prediction_decile) SELECT SUM(n*ABS(pred-actual))/SUM(n) weighted_abs_gap FROM d;
```

**解题逻辑：** 按十分位样本数加权。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 26. [Hard] 寻找所有孤立记录

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“寻找所有孤立记录”的明细或聚合结果。

```sql
SELECT 'prediction_without_feature' issue,p.id FROM ev_model_predictions p LEFT JOIN ev_customer_features f ON f.id=p.id WHERE f.id IS NULL UNION ALL SELECT 'segment_without_feature',s.id FROM ev_customer_segments s LEFT JOIN ev_customer_features f ON f.id=s.id WHERE f.id IS NULL;
```

**解题逻辑：** 双向反连接检查。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 27. [Hard] 对模型版本做组内排名

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“对模型版本做组内排名”的明细或聚合结果。

```sql
SELECT experiment_group,model_name,model_version,roc_auc,DENSE_RANK() OVER(PARTITION BY experiment_group ORDER BY roc_auc DESC) rnk FROM ev_model_metrics WHERE roc_auc IS NOT NULL;
```

**解题逻辑：** 在实验组内公平比较。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 28. [Hard] 生成训练与测试画像差异

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“生成训练与测试画像差异”的明细或聚合结果。

```sql
WITH x AS (SELECT source_set,city_type,COUNT(*)/SUM(COUNT(*)) OVER(PARTITION BY source_set) share FROM ev_customer_features GROUP BY source_set,city_type) SELECT a.city_type,a.share train_share,b.share test_share,b.share-a.share delta FROM x a JOIN x b ON a.city_type=b.city_type WHERE a.source_set='train' AND b.source_set='test';
```

**解题逻辑：** 自连接两个集合的占比。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 29. [Hard] 按城市和补贴做条件转化矩阵

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“按城市和补贴做条件转化矩阵”的明细或聚合结果。

```sql
SELECT city_type,AVG(CASE WHEN subsidy_available='Yes' THEN will_buy_ev='Yes' END) subsidy_yes_rate,AVG(CASE WHEN subsidy_available='No' THEN will_buy_ev='Yes' END) subsidy_no_rate FROM ev_customer_features WHERE source_set='train' GROUP BY city_type;
```

**解题逻辑：** 条件聚合生成宽表。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。

## 30. [Hard] 找概率相同但分群不同的客户对

**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。

**预期输出：** 能直接回答“找概率相同但分群不同的客户对”的明细或聚合结果。

```sql
WITH x AS (SELECT id,ROUND(segmentation_score,3) score_bin,customer_segment FROM ev_customer_segments) SELECT a.score_bin,a.customer_segment segment_a,b.customer_segment segment_b,COUNT(*) pair_count FROM x a JOIN x b ON a.score_bin=b.score_bin AND a.customer_segment<b.customer_segment GROUP BY a.score_bin,a.customer_segment,b.customer_segment HAVING COUNT(*)>=100;
```

**解题逻辑：** 用分箱控制浮点比较，再做自连接。

**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。

**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。

**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。

**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。
