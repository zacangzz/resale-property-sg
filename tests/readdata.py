# %%
from pathlib import Path

import pandas as pd

# %%

# %%
try:
    base_path = Path(__file__).parent
except NameError:
    base_path = Path.cwd()

data_candidates = [
    base_path / "../data/hdbresale_transactions_transformed.parquet",
    base_path / "data/hdbresale_transactions_transformed.parquet",
]
data_path = next(path for path in data_candidates if path.exists())
df = pd.read_parquet(data_path)
df.info()
# %%
