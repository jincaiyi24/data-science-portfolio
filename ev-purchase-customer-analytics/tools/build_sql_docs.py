from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


CHAPTERS = [
    ("项目问题与数据边界", "把购买意向排序、客户画像和模型验证放进同一分析链路，同时承认数据为合成数据、目标是意向而非成交。", "README.md；reports/project_audit.md", "原始竞赛数据、OOF 预测、测试集预测", "可验证的问题定义和限制说明", "先界定证据边界，才能避免把相关性说成因果。"),
    ("MySQL 在本项目中的角色", "MySQL 负责关系建模、质量门禁、可复用查询和业务结果导出，不负责重新训练模型。", "scripts/run_mysql_pipeline.py", "Python 已产出的特征、预测、分群和指标", "数据库表、查询结果与对账记录", "让建模结果能被分析师、BI 和面试官独立复核。"),
    ("为什么采用四表模型", "特征、预测、分群、实验指标具有不同粒度和更新节奏，拆表后责任清楚。", "sql/01_schema.sql", "四类实体", "四张规范化表及外键", "避免一张超宽表混合事实、派生标签和实验元数据。"),
    ("主键设计", "三个客户级表都使用全局唯一 id；指标表使用自增 metric_id。", "sql/01_schema.sql", "训练集 id 0-668664；测试集 id 668665-955235", "稳定的一对一连接键", "数据核验确认 train/test id 区间不重叠，因此 id 可单独做主键。"),
    ("外键与参照完整性", "预测和分群必须先有客户特征记录，删除客户时级联清理派生记录。", "sql/01_schema.sql", "客户、预测和分群 id", "两条外键约束", "把漏预测、孤立分群从静默错误变成装载失败。"),
    ("索引设计", "为 source_set、city、subsidy、segment、decile 和 probability 建立查询导向索引。", "docs/sql/index_design.md", "常用 WHERE、JOIN、GROUP BY 和 ORDER BY 列", "二级索引与 EXPLAIN 报告", "索引服务真实查询，不为展示语法而堆砌。"),
    ("环境变量与连接安全", "连接参数来自 .env 或 DATABASE_URL，日志只显示掩码地址。", "src/mysql/connection.py；.env.example", "host、port、user、password、database", "SQLAlchemy Engine", "避免密码进入代码、README、日志和 Git 历史。"),
    ("数据库创建与幂等性", "数据库和表使用 IF NOT EXISTS；数据刷新只清空本项目四表。", "src/mysql/connection.py；src/mysql/schema.py", "数据库名和 DDL", "可重复运行的结构", "一键脚本失败后可以修复配置再重跑。"),
    ("训练集与测试集合并", "统一字段后增加 source_set，测试集目标保留 NULL。", "src/mysql/loader.py::_prepare_features", "train.csv、test.csv", "955236 行客户特征", "既可全量画像，又不会把未知测试标签伪装成 No。"),
    ("真实 OOF 与测试预测", "训练行使用 advanced blend OOF，测试行使用对应真实 test prediction。", "src/mysql/loader.py::_prepare_predictions", "advanced_blend_oof/test_predictions.csv", "955236 行概率", "训练行不能使用全量拟合后的 in-sample 预测，否则验证分析会泄漏。"),
    ("预测十分位和百分位", "在 train/test 各自内部排名，1 表示最高十分位，百分位越高代表倾向越高。", "src/mysql/loader.py::_rank_predictions", "predicted_probability", "prediction_decile、prediction_percentile", "分别排名避免两个集合样本量不同造成分箱偏移。"),
    ("既有客户分群复用", "分群沿用多随机种子 XGBoost 业务模型及原规则，不用最终竞赛特征重新定义。", "src/business_analysis.py；src/mysql/loader.py::_prepare_segments", "dashboard 行级分群结果", "六类 customer_segment", "业务可解释性和比赛最优分数是两个目标，不能事后偷换口径。"),
    ("模型指标入库", "汇总模型比较、逐折结果、多种子稳定性、特征消融和融合实验。", "src/mysql/loader.py::_prepare_metrics", "outputs/tables/*.csv", "55 条真实实验记录", "NULL 表示原实验未产出该指标，不补造数字。"),
    ("分块装载", "pandas.to_sql 按块写入，失败时缩小块大小并最多重试三次。", "src/mysql/loader.py::_load_frame", "四张 DataFrame", "装载日志和数据库记录", "接近三百万行写入时，分块能控制内存与单次报文大小。"),
    ("事务与安全刷新", "在单连接中暂时关闭外键检查，按子表到父表顺序 TRUNCATE，再恢复约束。", "src/mysql/loader.py::load_tables", "已存在的本项目表", "干净的全量快照", "全量快照比逐行 upsert 更简单；生产增量场景应改用 staging + merge。"),
    ("数据质量门禁", "核验行数、唯一性、目标缺失规则、概率范围与连接覆盖率。", "src/mysql/validator.py；sql/02_data_quality.sql", "数据库四表和本地预期行数", "mysql_validation.csv/report.md", "把可复现性从一句承诺变成机器可判定的 PASS/FAIL。"),
    ("客户画像 SQL", "CASE WHEN 生成年龄和收入分层，GROUP BY 比较城市画像。", "sql/03_customer_profile.sql", "训练集客户特征", "画像组合的规模、购买率和均值", "只在有真实标签的训练集计算 observed purchase rate。"),
    ("倾向分析 SQL", "CTE 先完成三表连接，再按城市、补贴、充电和焦虑维度聚合。", "sql/04_purchase_propensity.sql", "特征与最终模型预测", "分组客户量和平均倾向", "CTE 让派生数据集只定义一次，主查询更易审查。"),
    ("连接覆盖率", "LEFT JOIN 保留全部客户，统计预测或分群缺口。", "sql/06_join_analysis.sql", "三张客户级表", "train/test 连接率", "INNER JOIN 会吞掉缺失行，无法发现覆盖问题。"),
    ("窗口函数", "使用 SUM OVER、DENSE_RANK、ROW_NUMBER 和 LAG 做组内占比、排序与差距。", "sql/07_window_functions.sql", "城市、收入层和分群聚合", "组内排名和前后差", "窗口函数保留明细层级，普通 GROUP BY 做不到。"),
    ("模型与实际结果比较", "在训练集十分位上比较平均预测与实际正例率，观察排序和校准差。", "sql/09_model_validation.sql", "真实 OOF 概率和 actual_target", "十分位校准表", "ROC-AUC 衡量排序而非概率校准，两者需要分开检查。"),
    ("业务 KPI 边界", "只计算客户数、意向率、模型倾向、充电和补贴等数据支持的 KPI。", "sql/10_business_kpi.sql", "四表可验证字段", "一行核心 KPI", "没有交易、成本和营收数据，因此不虚构 GMV、CAC、LTV 或 ROI。"),
    ("Python 与 SQL 对账", "同一组指标分别由 pandas 和 MySQL 计算，差异超过 1e-10 即失败。", "src/mysql/exporter.py", "内存表与数据库表", "13_python_sql_reconciliation.csv", "对账能发现分母、NULL 处理和过滤口径的不一致。"),
    ("查询性能分析", "对代表性聚合和窗口查询执行 EXPLAIN，结合访问类型、key 和 rows 判断。", "src/mysql/query_runner.py::write_performance_report", "三条核心 SQL", "query_performance_report.md", "低基数字段即使有索引，全表聚合仍可能选择扫描，这是成本模型的正常决策。"),
    ("复现、发布与审计", "一键脚本、输出清单、敏感信息扫描和公开包边界共同构成可交付证据。", "scripts/run_mysql_pipeline.py；tools/build_github_safe_package.ps1", "代码、配置模板和本地数据", "可运行项目与安全公开包", "公开仓库排除原始数据、行级客户结果、预测、模型和凭据。"),
]


INTERVIEW_TOPICS = [
    ("为什么选 MySQL 而不是只用 pandas？", "pandas 适合建模前处理，MySQL 更适合关系约束、共享查询、BI 接入和可审计结果。", "若数据只有几千行且无共享需求，数据库收益会降低。"),
    ("四张表为什么不合并？", "四类数据更新节奏、含义和粒度不同，拆表减少重复并防止模型字段污染原始特征。", "在线服务若追求低延迟，可建立经验证的宽表或物化视图。"),
    ("为什么 id 可以做单列主键？", "实测训练 id 为 0-668664、测试 id 为 668665-955235，全集无重叠。", "若不同批次会重复 id，应改为 source_set + id 复合主键。"),
    ("OOF 预测是什么？", "每个训练样本的预测都来自未见过该样本的折模型，可用于无泄漏评估与训练集业务排序。", "它仍依赖折分设计；时间数据应使用时间切分。"),
    ("为什么测试集 target 是 NULL？", "测试标签未知，NULL 表示事实缺失；写成 No 会制造错误标签并扭曲 KPI。", "SQL 聚合时必须明确训练集过滤。"),
    ("最终模型和分群模型为什么不同？", "最终模型追求竞赛 AUC，分群模型强调基础特征和稳定可解释性；两条轨道均有既有证据。", "上线时应建立模型治理，明确每个分数的 owner 和用途。"),
    ("十分位 1 为什么代表最高？", "业务通常把 Top Decile 作为优先触达群，因此降序排名后把最前 10% 标为 1。", "必须在数据字典注明方向，避免仪表盘误读。"),
    ("如何证明没有漏装数据？", "本地与数据库行数一致、id 唯一、预测和分群连接覆盖率为 100%，并输出验证表。", "还可加入哈希总计或抽样逐行比对。"),
    ("为什么用外键？", "保证预测和分群不能脱离客户存在，减少孤儿记录。", "超大批量装载时可先 staging，再在交换前验证约束。"),
    ("为什么要索引 source_set？", "大量查询只分析训练或测试集合，source_set 是高频过滤字段。", "它基数低，优化器可能对全量聚合仍选择扫描。"),
    ("联合索引顺序如何定？", "按高频过滤前缀和排序需求决定，例如 source_set + prediction_decile。", "索引不能同时完美服务所有查询，要用 EXPLAIN 和真实负载验证。"),
    ("什么是覆盖索引？", "查询所需列全部在索引中，可减少回表。", "本项目聚合需要很多列，盲目做宽覆盖索引会增加写入成本。"),
    ("CTE 的价值是什么？", "把连接或派生逻辑命名一次，提高主查询可读性和复用性。", "MySQL 优化器可能合并或物化 CTE，应通过 EXPLAIN 判断。"),
    ("窗口函数和 GROUP BY 区别？", "GROUP BY 压缩行；窗口函数在保留结果行的同时计算组内排名、累计或前后差。", "窗口排序通常需要临时表或 filesort。"),
    ("ROW_NUMBER 与 DENSE_RANK 区别？", "ROW_NUMBER 永不并列；DENSE_RANK 同值并列且名次不跳号。", "业务榜单要先决定同分是否并列。"),
    ("LAG 在项目里做什么？", "比较当前分群与前一名分群的平均倾向差。", "排序方向决定差值符号，必须在输出中解释。"),
    ("LEFT JOIN 为什么用于质量检查？", "它保留左表全集，从而能用右表 NULL 识别缺失匹配。", "WHERE 条件写在右表列上可能把 LEFT JOIN 意外变成 INNER JOIN。"),
    ("INNER JOIN 何时使用？", "确认覆盖完整后，分析需要三表字段时用 INNER JOIN，使意图清晰。", "质量检查阶段仍应使用 LEFT JOIN。"),
    ("COUNT(*) 和 COUNT(column) 差异？", "COUNT(*) 计行，COUNT(column) 忽略 NULL；连接覆盖用两者差异识别缺口。", "对可空字段使用 COUNT(column) 时不要误当总行数。"),
    ("AVG(condition) 为什么可算比例？", "MySQL 布尔表达式返回 0/1，AVG 就是满足条件的比例。", "NULL 会被忽略，分母口径必须审查。"),
    ("如何处理 SQL 中的 NULL？", "用 IS NULL、CASE 和明确过滤；不能用 = NULL。", "COALESCE 会改变含义，只在业务上确有默认值时使用。"),
    ("为何不用存储过程装载？", "数据源是 CSV 与 pandas 产物，Python 更适合模式映射、文件核验和跨平台日志。", "纯数据库生产环境可改用 LOAD DATA + 存储过程。"),
    ("to_sql 有什么限制？", "便利但不是最快；超大数据可能改用 LOAD DATA LOCAL INFILE。", "本项目通过分块、重试和行数验证换取实现清晰。"),
    ("为什么全量刷新用 TRUNCATE？", "本项目是可重建快照，TRUNCATE 快且避免重复。", "生产增量不能直接套用，应使用 staging、主键 upsert 和水位线。"),
    ("事务能否覆盖 TRUNCATE？", "MySQL DDL 会隐式提交，因此这里依靠可重跑全量快照和末端验证，而非宣称完全原子。", "更严格方案是装入 shadow tables 后 RENAME TABLE 原子交换。"),
    ("如何设计增量更新？", "按批次时间或源版本写 staging，校验后用 INSERT ... ON DUPLICATE KEY UPDATE 合并。", "需要删除语义时再加软删除或变更日志。"),
    ("如何防止 SQL 注入？", "值参数使用 SQLAlchemy text 绑定；数据库名仅允许字母数字下划线。", "表名和列名不能直接接受未经验证的用户输入。"),
    ("密码如何保护？", ".env 本地保存且被 Git 忽略，.env.example 只有占位值，日志掩码。", "生产应使用 Secret Manager 和短期凭据。"),
    ("如何解释 ROC-AUC？", "随机抽一名正例和负例，模型把正例排在前面的概率。", "AUC 不代表概率校准，也不直接等于业务收益。"),
    ("为什么校准差重要？", "同一十分位平均预测与实际正例率的差能揭示概率偏高或偏低。", "排序优秀的模型仍可能需要 Platt 或 isotonic 校准。"),
    ("为什么不计算 Accuracy 排名？", "比赛指标是 ROC-AUC，概率排序是核心；Accuracy 依赖阈值。", "业务决策需要结合成本选择阈值。"),
    ("高潜客户怎么定义？", "沿用现有分群规则：业务模型预测位于训练参考分布前 20%。", "规则优先级会覆盖后续条件，必须按代码顺序解释。"),
    ("Infrastructure-Constrained 如何定义？", "预测不低于中位数、无家庭充电且附近站点位于低四分位。", "只有 2505 名训练客户，行动前要检查样本和执行成本。"),
    ("为何不把分群当因果结论？", "分群来自相关特征和预测，未经过随机试验。", "营销效果应通过对照组验证增量 lift。"),
    ("为何不能算 ROI？", "数据没有触达成本、转化收入或真实购买记录。", "可以设计 ROI 公式和所需字段，但不能填写虚构结果。"),
    ("Python-SQL 对账为何设 1e-10？", "当前指标是同一浮点数据上的均值和计数，理论差异应接近机器精度。", "涉及 DECIMAL 舍入时应按业务精度放宽。"),
    ("如何检查数据漂移？", "按 source_set 比较分布、类别比例和 PSI/KS，但测试集漂移不等于标签漂移。", "上线还需按时间监控输入和性能。"),
    ("为什么模型指标允许 NULL？", "并非每次实验都记录 Accuracy、耗时或逐折结果，NULL 表示未产出。", "不能用 0 代替，否则会被误解为真实成绩。"),
    ("如何保证 SQL 输出可复现？", "命名查询、固定源文件、固定分群规则、一键脚本和 CSV 日志共同约束。", "数据库与依赖版本仍应记录。"),
    ("EXPLAIN 重点看什么？", "type、possible_keys、key、rows、filtered 和 Extra。", "估算 rows 不是实际耗时；必要时使用 EXPLAIN ANALYZE。"),
    ("为什么有索引仍可能全表扫描？", "查询返回比例高或需要全表聚合时，扫描成本可能低于大量随机回表。", "索引存在不等于必然使用。"),
    ("怎样优化窗口查询？", "先过滤、先聚合缩小行数，再对小结果集开窗；为过滤和连接键建索引。", "窗口本身的排序成本通常无法完全消除。"),
    ("如何验证索引有效？", "对代表性查询比较 EXPLAIN、实际耗时与扫描行数，并观察写入开销。", "只看索引列表不能证明收益。"),
    ("为什么公开包排除行级预测？", "比赛代码虽已先在 Kaggle 公开，但原始/行级数据、模型和提交仍不适合进入 GitHub 作品包。", "公开聚合指标和可复现代码即可展示能力。"),
    ("怎样向业务方解释两个模型分数？", "0.945713 是竞赛最终融合 OOF；0.941993 是可解释业务分群模型 OOF。", "两者回答的问题不同，不能只说一个“项目准确率”。"),
    ("项目最大的技术风险？", "合成数据与竞赛特征可能无法迁移到真实用户；测试标签不可见。", "需要真实时间外验证、校准和实验闭环。"),
    ("项目最大的 SQL 风险？", "全量快照装载时间和 DDL 非原子，失败时可能留下部分状态。", "生产化应使用 staging 表与原子换表。"),
    ("如果数据翻十倍怎么办？", "优先批量加载、分区/列式分析引擎、增量计算和预聚合。", "是否换技术栈取决于 SLA，而不是单看行数。"),
    ("如何为 Power BI 服务？", "SQL 导出稳定聚合 CSV，也可让 BI 只读连接到视图。", "生产连接应限制权限并避免 BI 扫描原始大表。"),
    ("你在项目中独立做了什么判断？", "把竞赛预测和业务分群分轨、拒绝虚构交易 KPI、用 OOF 入库并建立 Python-SQL 对账。", "这些判断比单纯堆 SQL 语法更能说明数据治理能力。"),
]


CODING_CASES = [
    ("Easy", "统计训练和测试行数", "SELECT source_set, COUNT(*) AS customers FROM ev_customer_features GROUP BY source_set;", "按 source_set 聚合。"),
    ("Easy", "检查重复客户 id", "SELECT id, COUNT(*) AS n FROM ev_customer_features GROUP BY id HAVING COUNT(*) > 1;", "HAVING 过滤聚合结果。"),
    ("Easy", "找出概率越界记录", "SELECT * FROM ev_model_predictions WHERE predicted_probability NOT BETWEEN 0 AND 1;", "用业务域约束筛查。"),
    ("Easy", "计算训练集购买意向率", "SELECT AVG(will_buy_ev='Yes') AS rate FROM ev_customer_features WHERE source_set='train';", "布尔均值等于比例。"),
    ("Easy", "按城市统计客户数", "SELECT city_type, COUNT(*) customers FROM ev_customer_features GROUP BY city_type ORDER BY customers DESC;", "基本分组排序。"),
    ("Easy", "统计有家庭充电的占比", "SELECT AVG(home_charging_possible='Yes') AS share FROM ev_customer_features;", "明确总体分母。"),
    ("Easy", "查看最高概率的 20 名测试客户", "SELECT id, predicted_probability FROM ev_model_predictions WHERE source_set='test' ORDER BY predicted_probability DESC LIMIT 20;", "过滤后降序取 Top N。"),
    ("Easy", "列出全部客户分群", "SELECT customer_segment, COUNT(*) customers FROM ev_customer_segments GROUP BY customer_segment;", "检查分群分布。"),
    ("Easy", "找出缺失训练标签", "SELECT id FROM ev_customer_features WHERE source_set='train' AND will_buy_ev IS NULL;", "集合条件与 NULL 判断。"),
    ("Easy", "查询最优 AUC 记录", "SELECT model_name, model_version, roc_auc FROM ev_model_metrics WHERE roc_auc IS NOT NULL ORDER BY roc_auc DESC LIMIT 1;", "过滤 NULL 后排序。"),
    ("Medium", "检查预测连接覆盖率", "SELECT COUNT(p.id)/COUNT(*) coverage FROM ev_customer_features f LEFT JOIN ev_model_predictions p ON p.id=f.id;", "LEFT JOIN 保留分母。"),
    ("Medium", "比较补贴组购买率", "SELECT subsidy_available, COUNT(*) n, AVG(will_buy_ev='Yes') rate FROM ev_customer_features WHERE source_set='train' GROUP BY subsidy_available;", "仅使用有标签集合。"),
    ("Medium", "计算各分群相对总体提升", "WITH b AS (SELECT AVG(will_buy_ev='Yes') r FROM ev_customer_features WHERE source_set='train') SELECT s.customer_segment, AVG(f.will_buy_ev='Yes')-b.r lift FROM ev_customer_segments s JOIN ev_customer_features f ON f.id=s.id CROSS JOIN b WHERE f.source_set='train' GROUP BY s.customer_segment,b.r;", "CTE 保存总体基线。"),
    ("Medium", "按城市给分群倾向排序", "WITH x AS (SELECT f.city_type,s.customer_segment,AVG(p.predicted_probability) score FROM ev_customer_features f JOIN ev_customer_segments s ON s.id=f.id JOIN ev_model_predictions p ON p.id=f.id GROUP BY f.city_type,s.customer_segment) SELECT *,DENSE_RANK() OVER(PARTITION BY city_type ORDER BY score DESC) rnk FROM x;", "先聚合再开窗。"),
    ("Medium", "计算每个十分位的实际正例率", "SELECT p.prediction_decile,COUNT(*) n,AVG(p.actual_target) actual_rate FROM ev_model_predictions p WHERE p.source_set='train' GROUP BY p.prediction_decile ORDER BY p.prediction_decile;", "actual_target 为 0/1。"),
    ("Medium", "找高倾向但充电受限客户", "SELECT f.id,p.predicted_probability FROM ev_customer_features f JOIN ev_model_predictions p ON p.id=f.id WHERE p.prediction_decile<=2 AND f.home_charging_possible='No' AND f.charging_stations_near_home+f.charging_stations_near_work<=3;", "连接特征与预测并组合条件。"),
    ("Medium", "统计分群在各城市的占比", "WITH x AS (SELECT f.city_type,s.customer_segment,COUNT(*) n FROM ev_customer_features f JOIN ev_customer_segments s ON s.id=f.id GROUP BY f.city_type,s.customer_segment) SELECT *,n/SUM(n) OVER(PARTITION BY city_type) share FROM x;", "窗口总和保留分群行。"),
    ("Medium", "找第二高倾向分群", "WITH x AS (SELECT customer_segment,AVG(segmentation_score) score,DENSE_RANK() OVER(ORDER BY AVG(segmentation_score) DESC) rnk FROM ev_customer_segments GROUP BY customer_segment) SELECT * FROM x WHERE rnk=2;", "DENSE_RANK 处理并列。"),
    ("Medium", "比较每个模型不同折的稳定性", "SELECT model_name,AVG(roc_auc) mean_auc,STDDEV_POP(roc_auc) std_auc,MIN(roc_auc) min_auc,MAX(roc_auc) max_auc FROM ev_model_metrics WHERE fold IS NOT NULL GROUP BY model_name;", "逐折记录聚合。"),
    ("Medium", "识别 source_set 不一致", "SELECT f.id FROM ev_customer_features f JOIN ev_model_predictions p ON p.id=f.id JOIN ev_customer_segments s ON s.id=f.id WHERE f.source_set<>p.source_set OR f.source_set<>s.source_set;", "连接后核对冗余标签。"),
    ("Hard", "计算累积 Top-k 客户覆盖的正例占比", "WITH r AS (SELECT actual_target,ROW_NUMBER() OVER(ORDER BY predicted_probability DESC) rn,COUNT(*) OVER() n,SUM(actual_target) OVER() positives FROM ev_model_predictions WHERE source_set='train'), c AS (SELECT rn,n,SUM(actual_target) OVER(ORDER BY rn) cum_pos,positives FROM r) SELECT rn/n population_share,cum_pos/positives positive_coverage FROM c WHERE rn IN (66867,133733,200600);", "排序后做累计正例覆盖。"),
    ("Hard", "计算十分位 lift", "WITH d AS (SELECT prediction_decile,AVG(actual_target) rate FROM ev_model_predictions WHERE source_set='train' GROUP BY prediction_decile), b AS (SELECT AVG(actual_target) rate FROM ev_model_predictions WHERE source_set='train') SELECT d.prediction_decile,d.rate,d.rate/b.rate lift FROM d CROSS JOIN b;", "以总体正例率为基准。"),
    ("Hard", "比较相邻十分位分数差", "WITH d AS (SELECT prediction_decile,AVG(predicted_probability) score FROM ev_model_predictions WHERE source_set='test' GROUP BY prediction_decile) SELECT *,score-LAG(score) OVER(ORDER BY prediction_decile) gap FROM d;", "LAG 获取上一行。"),
    ("Hard", "每个城市取前 100 名客户", "WITH r AS (SELECT f.id,f.city_type,p.predicted_probability,ROW_NUMBER() OVER(PARTITION BY f.city_type ORDER BY p.predicted_probability DESC) rn FROM ev_customer_features f JOIN ev_model_predictions p ON p.id=f.id WHERE f.source_set='test') SELECT * FROM r WHERE rn<=100;", "分区排名实现 group Top N。"),
    ("Hard", "构建模型校准误差摘要", "WITH d AS (SELECT prediction_decile,AVG(predicted_probability) pred,AVG(actual_target) actual,COUNT(*) n FROM ev_model_predictions WHERE source_set='train' GROUP BY prediction_decile) SELECT SUM(n*ABS(pred-actual))/SUM(n) weighted_abs_gap FROM d;", "按十分位样本数加权。"),
    ("Hard", "寻找所有孤立记录", "SELECT 'prediction_without_feature' issue,p.id FROM ev_model_predictions p LEFT JOIN ev_customer_features f ON f.id=p.id WHERE f.id IS NULL UNION ALL SELECT 'segment_without_feature',s.id FROM ev_customer_segments s LEFT JOIN ev_customer_features f ON f.id=s.id WHERE f.id IS NULL;", "双向反连接检查。"),
    ("Hard", "对模型版本做组内排名", "SELECT experiment_group,model_name,model_version,roc_auc,DENSE_RANK() OVER(PARTITION BY experiment_group ORDER BY roc_auc DESC) rnk FROM ev_model_metrics WHERE roc_auc IS NOT NULL;", "在实验组内公平比较。"),
    ("Hard", "生成训练与测试画像差异", "WITH x AS (SELECT source_set,city_type,COUNT(*)/SUM(COUNT(*)) OVER(PARTITION BY source_set) share FROM ev_customer_features GROUP BY source_set,city_type) SELECT a.city_type,a.share train_share,b.share test_share,b.share-a.share delta FROM x a JOIN x b ON a.city_type=b.city_type WHERE a.source_set='train' AND b.source_set='test';", "自连接两个集合的占比。"),
    ("Hard", "按城市和补贴做条件转化矩阵", "SELECT city_type,AVG(CASE WHEN subsidy_available='Yes' THEN will_buy_ev='Yes' END) subsidy_yes_rate,AVG(CASE WHEN subsidy_available='No' THEN will_buy_ev='Yes' END) subsidy_no_rate FROM ev_customer_features WHERE source_set='train' GROUP BY city_type;", "条件聚合生成宽表。"),
    ("Hard", "找概率相同但分群不同的客户对", "WITH x AS (SELECT id,ROUND(segmentation_score,3) score_bin,customer_segment FROM ev_customer_segments) SELECT a.score_bin,a.customer_segment segment_a,b.customer_segment segment_b,COUNT(*) pair_count FROM x a JOIN x b ON a.score_bin=b.score_bin AND a.customer_segment<b.customer_segment GROUP BY a.score_bin,a.customer_segment,b.customer_segment HAVING COUNT(*)>=100;", "用分箱控制浮点比较，再做自连接。"),
]


def build_master_guide() -> str:
    parts = ["# EV SQL 项目完整学习手册", "", "> 本手册以项目中的真实文件、真实预测和真实指标为准；没有交易数据，因此不推导 GMV、ROI、CAC 或 LTV。", ""]
    for i, (title, concept, code, source, output, reason) in enumerate(CHAPTERS, 1):
        if "sql/" in code:
            example = f"-- Executable reference: {code}\nSELECT COUNT(*) AS checked_rows FROM ev_customer_features;"
            language = "sql"
        elif "connection.py" in code:
            example = "settings = load_settings()\nengine = create_database_engine(settings)"
            language = "python"
        elif "loader.py" in code:
            example = "tables = prepare_tables(ROOT)\nload_tables(engine, tables, OUTPUT_DIR, chunk_size=5000)"
            language = "python"
        elif "validator.py" in code or "exporter.py" in code or "query_runner.py" in code:
            example = "python scripts/run_mysql_pipeline.py --skip-load"
            language = "bash"
        else:
            example = "python scripts/run_mysql_pipeline.py"
            language = "bash"
        parts.extend([
            f"## 第 {i} 章 {title}", "",
            f"**概念是什么：** {concept}", "",
            f"**为什么本项目需要：** {reason}", "",
            f"**代码位置：** `{code}`", "",
            "**代码示例：**", "", f"```{language}", example, "```", "",
            f"**输入：** {source}", "",
            f"**输出：** {output}", "",
            "**先后逻辑：** 先确认输入口径和唯一键，再执行转换或查询，最后用行数、范围或连接覆盖进行验证。", "",
            "**为什么这样写：** 选择最直接且可审计的实现，让代码、SQL 和导出结果能够互相追溯。", "",
            "**替代方案：** 小数据可完全用 pandas；生产大数据可使用 staging、批量加载、调度器和数据仓库。替代方案是否更好取决于并发、延迟和治理要求。", "",
            "**常见错误：** 混淆训练/测试口径、把 NULL 当 0、用 INNER JOIN 掩盖缺口、把相关性当因果，或在没有原始证据时补造指标。", "",
            f"**面试回答：** 我在本项目中用这一设计解决了“{title}”问题，并通过自动验证与导出结果证明实现可复现。", "",
            "**高级追问：** 如果数据量扩大十倍或改为每日增量，当前方案哪里先成为瓶颈？", "",
            "**参考答案：** 全量 CSV 读取和 TRUNCATE 重载会先受到 I/O 与恢复时间限制；应改成 staging 表、增量水位、批量装载和原子换表，并保留同样的质量门禁。", "",
        ])
    return "\n".join(parts)


def build_interview() -> str:
    parts = ["# EV SQL 面试问答", "", f"共 {len(INTERVIEW_TOPICS)} 题。回答均基于本项目实际结构和结果。", ""]
    for i, (question, answer, follow_up) in enumerate(INTERVIEW_TOPICS, 1):
        parts.extend([f"## {i}. {question}", "", f"**核心回答：** {answer}", "", f"**深挖追问与回答：** {follow_up}", ""])
    return "\n".join(parts)


def build_coding_questions() -> str:
    parts = ["# EV SQL Coding Questions", "", f"共 {len(CODING_CASES)} 题，覆盖 Easy / Medium / Hard。", ""]
    for i, (level, question, sql, logic) in enumerate(CODING_CASES, 1):
        parts.extend([
            f"## {i}. [{level}] {question}", "",
            "**题目与输入表：** 使用 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 或 `ev_model_metrics` 中与题意相关的字段。", "",
            f"**预期输出：** 能直接回答“{question}”的明细或聚合结果。", "",
            "```sql", sql, "```", "",
            f"**解题逻辑：** {logic}", "",
            "**实际执行结果：** 运行 `scripts/run_mysql_pipeline.py` 后，可在 MySQL Workbench 执行本题；核心项目查询的结果位于 `outputs/sql/`。", "",
            "**常见错误：** 忘记训练/测试过滤、连接键写错、在 WHERE 中误删 NULL，或排序方向与题意相反。", "",
            "**替代写法：** 多数题可改写为子查询、CTE 或条件聚合；选择应以清晰度和 EXPLAIN 结果为准。", "",
            "**面试官可能追问：** 数据量扩大后如何优化？回答应从过滤选择性、连接键索引、先聚合再开窗和扫描行数展开。", "",
        ])
    return "\n".join(parts)


def main() -> None:
    sql_docs = DOCS / "sql"
    interview_docs = DOCS / "interview"
    sql_docs.mkdir(parents=True, exist_ok=True)
    interview_docs.mkdir(parents=True, exist_ok=True)
    (sql_docs / "SQL_PROJECT_MASTER_GUIDE_CN.md").write_text(build_master_guide(), encoding="utf-8")
    (interview_docs / "EV_SQL_INTERVIEW_CN.md").write_text(build_interview(), encoding="utf-8")
    (interview_docs / "EV_SQL_CODING_QUESTIONS_CN.md").write_text(build_coding_questions(), encoding="utf-8")
    (interview_docs / "EV_SQL_PROJECT_PITCH_CN.md").write_text(
        """# EV SQL 项目表达稿

## 30 秒

我把一个电动车购买倾向竞赛项目补成了可执行的 MySQL 分析工程。项目将 95.5 万名客户的特征、真实 OOF/Test 预测、既有业务分群和 55 条模型实验指标拆成四张关系表，通过 Python 自动分块装载，并用 SQL 完成质量检查、画像、十分位、窗口排名和业务 KPI。最重要的设计是区分最终竞赛模型与业务分群模型，并用 Python-SQL 对账防止统计口径漂移。

## 1 分钟

这个项目原本有完整建模结果，但 SQL 只是静态示例。我负责把它改造成真正能运行的数据链路。首先确认训练和测试 id 全局唯一，再设计 `ev_customer_features`、`ev_model_predictions`、`ev_customer_segments` 和 `ev_model_metrics` 四张表，用主外键保证一对一覆盖。Python 从既有文件读取 95.5 万行客户数据，训练集只装真实 OOF，测试集装真实预测，分群沿用可解释业务模型，模型指标没有的字段保留 NULL。装载后自动执行 13 组查询与对账，验证行数、唯一性、概率范围和 join 覆盖率。这样既展示 MySQL，也保留了机器学习验证的严谨性。

## 3 分钟

我把项目分为模型事实层和数据库分析层。模型事实层不重新训练：最终竞赛轨道使用 Advanced + Base Blend，OOF ROC-AUC 为 0.945713；业务分群轨道沿用多随机种子 XGBoost，OOF ROC-AUC 为 0.941993。数据库层先把原始特征、模型输出、业务分群和实验指标分离，避免一张宽表同时承担来源数据和派生数据。预测表保存 source_set、真实标签、概率、十分位、百分位和版本；分群表保存原规则产生的六类人群和业务模型分数。

工程上，连接信息通过 `.env` 管理，日志不打印密码。`pandas.to_sql` 分块装载，失败自动缩小块大小。SQL 覆盖 CTE、CASE、JOIN、窗口函数、分组 Top N、十分位 lift、模型校准和业务 KPI。质量门禁会比较本地与 MySQL 行数、检查重复 id、未知测试标签、概率范围以及预测/分群连接覆盖。最后同一批指标在 pandas 和 SQL 中各算一次，差异超阈值就失败。这个流程说明我不只是会写查询，还能把模型结果做成可维护、可审计的数据产品。

## 5 分钟

这个项目的业务问题是识别更可能购买电动车的人群并解释其特征，但数据是合成客户数据，标签代表购买意向而非真实成交。因此我一开始就限制结论边界：可以谈关联、排序和人群策略，不能虚构 GMV、ROI、CAC 或因果效果。

原项目已有模型与预测，我没有为 SQL 工作重新调参。最终竞赛模型通过高级特征 XGBoost 与基础模型融合取得 0.945713 OOF AUC；业务分群则保留基础特征多种子模型，因为它更适合解释和稳定性分析。把两套模型分开是一个关键判断：前者优化比赛排序，后者服务业务沟通，不能只报一个模糊的“准确率”。

MySQL 采用四表模型。特征表是客户主实体；预测表与分群表通过外键一对一关联；指标表独立保存不同粒度的模型实验。训练和测试 id 经验证不重叠，所以可以使用单列主键。索引围绕 source_set、城市、补贴、分群、概率和十分位设计，并用 EXPLAIN 记录真实执行计划。

Python 一键脚本负责建库建表、读取文件、字段映射、分块装载、SQL 执行、CSV 导出和验证。训练预测严格使用 OOF，测试目标保持 NULL。所有业务分群都来自既有规则，而不是为了 SQL 展示临时造标签。装载后有三道检查：结构与行数门禁、SQL 查询导出、Python-SQL 指标对账。这样可以及时发现 INNER JOIN 吞行、NULL 分母变化或排序方向写反等问题。

最终交付不仅是 SQL 文件，还包括装载日志、13 份分析结果、性能报告、25 章学习手册、50 道面试问答和 30 道实战题。若把它生产化，我会把全量 TRUNCATE 重载改为 staging + 增量合并或原子换表，并将凭据迁移到 Secret Manager；模型侧还需要时间外验证、概率校准和营销随机对照实验。
""",
        encoding="utf-8",
    )
    print("SQL learning and interview documents generated.")


if __name__ == "__main__":
    main()
