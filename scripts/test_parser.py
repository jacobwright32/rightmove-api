"""Test expanded feature parser against all data."""
import sys
sys.path.insert(0, ".")

import pandas as pd
from app.feature_parser import parse_all_features

df = pd.read_parquet("sales_data/all_properties.parquet")
parsed = df["extra_features"].apply(parse_all_features).apply(pd.Series)
enriched = pd.concat([df, parsed], axis=1)

new_cols = [c for c in parsed.columns]
print(f"{len(enriched)} rows x {len(enriched.columns)} columns")
print(f"{len(new_cols)} extracted features\n")

for col in new_cols:
    filled = enriched[col].notna().sum()
    pct = 100 * filled / len(enriched)
    vals = enriched[col].dropna().value_counts().head(5)
    val_str = ", ".join(f"{v}={c}" for v, c in vals.items())
    print(f"  {col:20s} {filled:4d}/{len(enriched)} ({pct:4.1f}%)  {val_str}")

enriched.to_parquet("sales_data/enriched_properties.parquet", engine="pyarrow", compression="snappy", index=False)
print(f"\nSaved sales_data/enriched_properties.parquet ({len(enriched.columns)} columns)")
