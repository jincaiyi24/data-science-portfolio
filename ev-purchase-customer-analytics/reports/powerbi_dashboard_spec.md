# Power BI Dashboard Specification

## Page 1: Executive Overview

Use KPI cards for customers, observed purchase rate, mean predicted propensity and High Potential share. Add a segment bar chart and slicers for city, vehicle type and subsidy. Source: `customer_overview.csv` and `segment_analysis.csv`.

## Page 2: Customer Profile

Use age and income histograms, a city-type bar chart and a vehicle-type stacked bar. Axis: customer count or observed purchase rate; filters: segment, gender and charging status. Business question: which profiles combine scale and propensity?

## Page 3: Purchase Drivers

Use a horizontal feature-importance bar from `feature_driver.csv`, plus clustered bars for subsidy, environmental concern, range anxiety and charging. Business question: which attributes are associated with model scores and observed intent?

## Page 4: Customer Segments

Use a segment comparison matrix with customer count, share, predicted propensity, observed rate, income and charging share. Add a scatter plot: X = customer share, Y = propensity, size = customer count. Business question: where should differentiated campaigns focus?

The environment does not create a genuine `.pbix`; the supplied CSVs are Power BI-ready and the specification avoids a fake binary file.
