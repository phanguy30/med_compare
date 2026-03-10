import re
from pathlib import Path

import numpy as np
import pandas as pd
import umap

from sqlalchemy import create_engine, text
from scipy.sparse import csr_matrix, hstack
from sklearn.decomposition import TruncatedSVD


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = BASE_DIR / "rxnorm.sqlite"

OUTPUT_DIR = BASE_DIR / "precomputed"
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_EMBEDDING = OUTPUT_DIR / "global_umap_embedding.parquet"
OUTPUT_FEATURES = OUTPUT_DIR / "global_heatmap_features.parquet"

# Adjust these if your SQLite table names differ
RXNCONSO_TABLE = "RXNCONSO"
RXNREL_TABLE = "RXNREL"

# Your products are DP
PRODUCT_TTYS = ("DP",)

# Your current app uses SCDC on the ingredient side
INGREDIENT_TTY = "SCDC"

# Keep only ingredients seen in at least this many products
MIN_INGREDIENT_FREQ = 5

# Dose form stays in the dataframe so you can turn it on later
DOSEFORM_WEIGHT = 2.0
USE_DOSE_FORM_FEATURES = False   # set to True later when dose form is fixed

# Compression before UMAP
SVD_COMPONENTS = 100

# UMAP settings
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.10
UMAP_RANDOM_STATE = 42

# Optional relation filter for ingredients.
# Example: INGREDIENT_RELA_FILTER = "has_ingredient"
INGREDIENT_RELA_FILTER = None

# Optional relation filter for dose form.
# Example: DOSE_FORM_RELA_FILTER = "dose_form_of"
DOSE_FORM_RELA_FILTER = None


# ============================================================
# ENGINE
# ============================================================

print(f"Using SQLite file: {SQLITE_PATH}")
if not SQLITE_PATH.exists():
    raise FileNotFoundError(f"SQLite file not found: {SQLITE_PATH}")

sqlite_engine = create_engine(f"sqlite:///{SQLITE_PATH}")


# ============================================================
# HELPERS
# ============================================================

def parse_name_and_mg(full_str):
    """
    Parse strings like:
        'Acetaminophen 325 MG'
    into:
        ('Acetaminophen', 325.0)

    If no 'MG' pattern is found, returns the full string and 0.0.
    """
    full_str = str(full_str)
    match = re.search(r"(.+?)\s+(\d+(?:\.\d+)?)\s+MG\b", full_str, re.IGNORECASE)
    if match:
        return match.group(1).strip(), float(match.group(2))
    return full_str.strip(), 0.0


def inspect_tables(engine):
    """
    Print tables found in the SQLite database.
    """
    with engine.connect() as conn:
        tables = pd.read_sql(text("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
        """), conn)

    print("\nTables found in SQLite:")
    print(tables.to_string(index=False))


def fetch_all_products(engine):
    """
    Fetch all DP products from RXNCONSO.

    Returns
    -------
    pd.DataFrame
        Columns: ID, Product_Name, TTY
    """
    placeholders = ", ".join([f":tty{i}" for i in range(len(PRODUCT_TTYS))])
    params = {f"tty{i}": tty for i, tty in enumerate(PRODUCT_TTYS)}

    sql = text(f"""
        SELECT DISTINCT
            CAST(RXCUI AS TEXT) AS ID,
            STR AS Product_Name,
            TTY
        FROM {RXNCONSO_TABLE}
        WHERE TTY IN ({placeholders})
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)

    df["ID"] = df["ID"].astype(str)
    df = df.drop_duplicates(subset=["ID"], keep="first").reset_index(drop=True)
    return df


def fetch_all_ingredients_for_products(engine, product_ids):
    """
    Fetch all ingredient rows for all products in chunks.

    Mirrors your Fetch_Heatmap pattern:
        r.RXCUI1 = product
        c.RXCUI = r.RXCUI2
        c.TTY = 'SCDC'

    Returns
    -------
    pd.DataFrame
        Columns: ID, Full_Ingredient
    """
    if not product_ids:
        return pd.DataFrame(columns=["ID", "Full_Ingredient"])

    chunk_size = 5000
    chunks = []

    with engine.connect() as conn:
        for start in range(0, len(product_ids), chunk_size):
            batch = product_ids[start:start + chunk_size]
            placeholders = ", ".join([f":id{i}" for i in range(len(batch))])
            params = {f"id{i}": batch[i] for i in range(len(batch))}
            params["ingredient_tty"] = INGREDIENT_TTY

            rela_clause = ""
            if INGREDIENT_RELA_FILTER is not None:
                rela_clause = "AND r.RELA = :ingredient_rela"
                params["ingredient_rela"] = INGREDIENT_RELA_FILTER

            sql = text(f"""
                SELECT
                    CAST(r.RXCUI1 AS TEXT) AS ID,
                    c.STR AS Full_Ingredient
                FROM {RXNREL_TABLE} r
                JOIN {RXNCONSO_TABLE} c
                    ON CAST(c.RXCUI AS TEXT) = CAST(r.RXCUI2 AS TEXT)
                WHERE CAST(r.RXCUI1 AS TEXT) IN ({placeholders})
                  AND c.TTY = :ingredient_tty
                  {rela_clause}
            """)

            chunk_df = pd.read_sql(sql, conn, params=params)
            chunks.append(chunk_df)

            print(
                f"Ingredient chunk {start // chunk_size + 1}: "
                f"{len(batch):,} products -> {len(chunk_df):,} rows"
            )

    if not chunks:
        return pd.DataFrame(columns=["ID", "Full_Ingredient"])

    out = pd.concat(chunks, ignore_index=True)
    out["ID"] = out["ID"].astype(str)
    return out


def fetch_all_dose_forms(engine, product_ids):
    """
    Fetch one dose form per product.

    Returns
    -------
    pd.DataFrame
        Columns: ID, Dose_Form
    """
    if not product_ids:
        return pd.DataFrame(columns=["ID", "Dose_Form"])

    chunk_size = 5000
    chunks = []

    with engine.connect() as conn:
        for start in range(0, len(product_ids), chunk_size):
            batch = product_ids[start:start + chunk_size]
            placeholders = ", ".join([f":id{i}" for i in range(len(batch))])
            params = {f"id{i}": batch[i] for i in range(len(batch))}

            rela_clause = ""
            if DOSE_FORM_RELA_FILTER is not None:
                rela_clause = "AND r.RELA = :dose_form_rela"
                params["dose_form_rela"] = DOSE_FORM_RELA_FILTER

            sql = text(f"""
                SELECT
                    CAST(r.RXCUI1 AS TEXT) AS ID,
                    c.STR AS Dose_Form
                FROM {RXNREL_TABLE} r
                JOIN {RXNCONSO_TABLE} c
                    ON CAST(c.RXCUI AS TEXT) = CAST(r.RXCUI2 AS TEXT)
                WHERE CAST(r.RXCUI1 AS TEXT) IN ({placeholders})
                  AND c.TTY = 'DF'
                  {rela_clause}
            """)

            chunk_df = pd.read_sql(sql, conn, params=params)
            chunks.append(chunk_df)

            print(
                f"Dose form chunk {start // chunk_size + 1}: "
                f"{len(batch):,} products -> {len(chunk_df):,} rows"
            )

    if not chunks:
        return pd.DataFrame(columns=["ID", "Dose_Form"])

    df = pd.concat(chunks, ignore_index=True)
    df["ID"] = df["ID"].astype(str)
    df = df.drop_duplicates(subset=["ID"], keep="first").reset_index(drop=True)
    return df


def build_global_heatmap_df(engine):
    """
    Build the all-drug version of your heatmap dataframe.

    Output columns:
        Product_Name
        ingredient columns...
        Ingredients_List
        ID
        Dose_Form
    """
    products_df = fetch_all_products(engine)
    product_ids = products_df["ID"].tolist()

    print(f"Fetched {len(products_df):,} DP products")

    ing_df = fetch_all_ingredients_for_products(engine, product_ids)
    print(f"Fetched {len(ing_df):,} product-ingredient rows")

    if ing_df.empty:
        raise ValueError(
            "No ingredient rows found. "
            "Check SQLITE_PATH, joins, TTY filters, and possible RELA filters."
        )

    parsed = ing_df["Full_Ingredient"].apply(parse_name_and_mg)
    ing_df["Ingredient"] = parsed.apply(lambda t: t[0])
    ing_df["Concentration"] = parsed.apply(lambda t: t[1])
    ing_df["Concentration"] = pd.to_numeric(
        ing_df["Concentration"], errors="coerce"
    ).fillna(0)

    ing_df = ing_df.merge(
        products_df[["ID", "Product_Name"]],
        on="ID",
        how="left"
    )

    ingredient_counts = (
        ing_df[["ID", "Ingredient"]]
        .drop_duplicates()
        .groupby("Ingredient")["ID"]
        .nunique()
        .reset_index(name="n_products")
    )

    keep_ingredients = set(
        ingredient_counts.loc[
            ingredient_counts["n_products"] >= MIN_INGREDIENT_FREQ, "Ingredient"
        ]
    )

    ing_df = ing_df.loc[ing_df["Ingredient"].isin(keep_ingredients)].copy()
    print(f"Kept {len(keep_ingredients):,} ingredients after frequency filter")

    if ing_df.empty:
        raise ValueError(
            "All ingredients were removed by MIN_INGREDIENT_FREQ. "
            "Try lowering that threshold."
        )

    heatmap_wide = (
        ing_df.pivot_table(
            index="ID",
            columns="Ingredient",
            values="Concentration",
            aggfunc="max",
            fill_value=0
        )
        .reset_index()
    )

    ingredient_list_df = (
        ing_df.groupby("ID")["Ingredient"]
        .apply(lambda s: sorted(set(s)))
        .reset_index(name="Ingredients_List")
    )

    product_name_df = (
        products_df[["ID", "Product_Name"]]
        .drop_duplicates(subset=["ID"], keep="first")
        .reset_index(drop=True)
    )

    dose_form_df = fetch_all_dose_forms(engine, product_ids)

    heatmap_df = (
        heatmap_wide
        .merge(ingredient_list_df, on="ID", how="left")
        .merge(product_name_df, on="ID", how="left")
        .merge(dose_form_df, on="ID", how="left")
    )

    heatmap_df["Dose_Form"] = heatmap_df["Dose_Form"].fillna("UNKNOWN")
    heatmap_df["ID"] = heatmap_df["ID"].astype(str)

    ingredient_cols = [
        c for c in heatmap_df.columns
        if c not in {"Product_Name", "Ingredients_List", "ID", "Dose_Form"}
    ]

    heatmap_df = heatmap_df[
        ["Product_Name"] + ingredient_cols + ["Ingredients_List", "ID", "Dose_Form"]
    ].copy()

    heatmap_df = heatmap_df.reset_index(drop=True)
    return heatmap_df


def build_sparse_umap_features(df, doseform_weight=2.0, use_dose_form_features=False):
    """
    Build sparse feature matrix.

    For now you can keep use_dose_form_features=False.
    Later, when dose form is fixed, turn it on without changing the rest
    of the pipeline.
    """
    ignore_cols = {"Product_Name", "Ingredients_List", "ID", "Dose_Form"}
    ingredient_cols = [c for c in df.columns if c not in ignore_cols]

    if not ingredient_cols:
        raise ValueError("No ingredient columns found in heatmap_df.")

    X_ing_dense = (
        df[ingredient_cols]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
        .to_numpy(dtype=np.float32)
    )
    X_ing = csr_matrix(X_ing_dense)

    if not use_dose_form_features:
        return X_ing, ingredient_cols, []

    df_form = df[["Dose_Form"]].copy()
    df_form["Dose_Form"] = df_form["Dose_Form"].fillna("UNKNOWN").astype(str)

    form_ohe = pd.get_dummies(df_form["Dose_Form"], prefix="DF").astype(np.float32)
    X_form = csr_matrix(
        form_ohe.to_numpy(dtype=np.float32) * np.float32(doseform_weight)
    )

    X = hstack([X_ing, X_form], format="csr", dtype=np.float32)
    return X, ingredient_cols, list(form_ohe.columns)


def fit_global_umap(X):
    """
    Fit global UMAP:
        sparse matrix -> TruncatedSVD -> UMAP
    """
    n_samples = X.shape[0]
    if n_samples < 3:
        raise ValueError(f"Need at least 3 products, got {n_samples}")

    max_valid_components = min(X.shape[0] - 1, X.shape[1] - 1)
    n_components = min(SVD_COMPONENTS, max_valid_components)

    if n_components < 2:
        raise ValueError(
            f"TruncatedSVD components too small after bounds check: {n_components}"
        )

    print(f"Running TruncatedSVD with n_components={n_components}")
    svd = TruncatedSVD(n_components=n_components, random_state=UMAP_RANDOM_STATE)
    X_reduced = svd.fit_transform(X)

    n_neighbors = min(UMAP_N_NEIGHBORS, n_samples - 1)
    n_neighbors = max(2, n_neighbors)

    print(f"Running UMAP on reduced matrix shape={X_reduced.shape}")
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=UMAP_MIN_DIST,
        n_components=2,
        metric="cosine",
        random_state=UMAP_RANDOM_STATE,
        low_memory=True,
        n_jobs=1,
        init="random"
    )

    embedding = reducer.fit_transform(X_reduced)
    return embedding, svd


def add_embedding_columns(df, embedding, jitter_strength=0.15, seed=42):
    """
    Add UMAP coordinates and jittered coordinates.
    """
    out = df.copy()
    out["UMAP1"] = embedding[:, 0]
    out["UMAP2"] = embedding[:, 1]

    out["Ingredients_Str"] = out["Ingredients_List"].apply(
        lambda x: ", ".join(x) if isinstance(x, list) else str(x)
    )

    rng = np.random.default_rng(seed)
    out["UMAP1_jitter"] = out["UMAP1"] + rng.normal(0, jitter_strength, len(out))
    out["UMAP2_jitter"] = out["UMAP2"] + rng.normal(0, jitter_strength, len(out))

    return out


def sanity_check_one_id(engine, test_id):
    """
    Optional debugging helper:
    inspect RXNREL rows for one DP ID to see whether RELA filters should be added.
    """
    q = text(f"""
        SELECT *
        FROM {RXNREL_TABLE}
        WHERE CAST(RXCUI1 AS TEXT) = :id
    """)

    with engine.connect() as conn:
        rel_df = pd.read_sql(q, conn, params={"id": str(test_id)})

    if rel_df.empty:
        print(f"No RXNREL rows found for ID={test_id}")
        return

    cols = [c for c in ["RXCUI1", "RXCUI2", "REL", "RELA"] if c in rel_df.columns]
    print(rel_df[cols].drop_duplicates().head(50))


def main():
    inspect_tables(sqlite_engine)

    print("\nBuilding global heatmap dataframe...")
    heatmap_df = build_global_heatmap_df(sqlite_engine)
    print(f"Global heatmap df shape: {heatmap_df.shape}")

    print("Building sparse feature matrix...")
    X, ingredient_cols, doseform_cols = build_sparse_umap_features(
        heatmap_df,
        doseform_weight=DOSEFORM_WEIGHT,
        use_dose_form_features=USE_DOSE_FORM_FEATURES
    )
    print(f"Sparse feature matrix shape: {X.shape}")

    print("Fitting global UMAP...")
    embedding, svd = fit_global_umap(X)

    print("Attaching embedding columns...")
    embedding_df = add_embedding_columns(heatmap_df, embedding)

    app_embedding_df = embedding_df[
        [
            "ID",
            "Product_Name",
            "Dose_Form",
            "Ingredients_List",
            "Ingredients_Str",
            "UMAP1",
            "UMAP2",
            "UMAP1_jitter",
            "UMAP2_jitter",
        ]
    ].copy()

    print(f"Saving embedding to: {OUTPUT_EMBEDDING}")
    app_embedding_df.to_parquet(OUTPUT_EMBEDDING, index=False)

    print(f"Saving full heatmap features to: {OUTPUT_FEATURES}")
    heatmap_df.to_parquet(OUTPUT_FEATURES, index=False)

    print("\nDone.")
    print(f"Products embedded: {len(app_embedding_df):,}")
    print(f"Ingredient columns: {len(ingredient_cols):,}")
    print(f"Dose form columns used in features: {len(doseform_cols):,}")
    print(f"Dose form feature flag: {USE_DOSE_FORM_FEATURES}")


if __name__ == "__main__":
    main()