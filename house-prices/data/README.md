# 数据说明

本目录不随作品包分发 Kaggle 原始比赛数据。

请从 Kaggle 比赛页下载并放置以下文件：

```text
data/
├── train.csv
├── test.csv
└── sample_submission.csv
```

比赛名称：`House Prices - Advanced Regression Techniques`

代码会检查：

- `train.csv` 为 1460 行、81 列；
- `test.csv` 为 1459 行、80 列；
- 训练和测试特征顺序一致；
- `Id` 唯一且训练、测试集合不重叠；
- `SalePrice` 只出现在训练集且没有缺失。

`data_description.txt` 可从同一比赛页取得，用于确认字段含义和结构性缺失值。
