# Data Files

Download the official competition files with:

```bash
kaggle competitions download -c playground-series-s6e9 -p data/raw --unzip
```

Expected files are `train.csv`, `test.csv` and `sample_submission.csv`. They are intentionally excluded from Git. The optional CC0 source-data transfer check expects `EV_Adoption_and_Range_Anxiety_Dataset.csv` under `data/external/`; external labels are not used by the final model.
