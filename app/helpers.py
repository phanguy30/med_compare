import os
import re
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import umap
from sqlalchemy import create_engine, text

from app.chart_helper import (
    _message_chart,
    _ensure_product_name,
    _apply_selection,
    _build_umap_features,
    _fit_umap,
    _add_embedding_columns,
    _make_default_heatmap_subset,
    _get_value_cols,
    _prepare_brushed_heatmap_input,
    _prepare_long_heatmap_df,
    _prepare_default_row_bands,
    _prepare_brushed_row_bands,
    _build_brush,
    _build_umap_chart,
    _build_default_heatmap_layers,
    _build_brushed_heatmap_layers,
)

alt.data_transformers.disable_max_rows()

# =========================================================
# PATHS
# =========================================================
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "rxnorm.sqlite"
PRECOMPUTED_DIR = BASE_DIR / "assets" / "precomputed"

PRECOMPUTED_DRUGS = {
    "tylenol": {
        "display_name": "Tylenol",
        "html_file": PRECOMPUTED_DIR / "tylenol_linked_plot.html",
    },
    "excedrin": {
        "display_name": "Excedrin",
        "html_file": PRECOMPUTED_DIR / "excedrin_linked_plot.html",
    },
}

# =========================================================
# DATABASE
# =========================================================
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)

def ensure_sqlite_indexes():
    stmts = [
        "CREATE INDEX IF NOT EXISTS idx_rxnconso_str ON RXNCONSO(STR);",
        "CREATE INDEX IF NOT EXISTS idx_rxnconso_rxcui ON RXNCONSO(RXCUI);",
        "CREATE INDEX IF NOT EXISTS idx_rxnconso_tty ON RXNCONSO(TTY);",
        "CREATE INDEX IF NOT EXISTS idx_rxnconso_tty_rxcui ON RXNCONSO(TTY, RXCUI);",
        "CREATE INDEX IF NOT EXISTS idx_rxnrel_rxcui1 ON RXNREL(RXCUI1);",
        "CREATE INDEX IF NOT EXISTS idx_rxnrel_rxcui2 ON RXNREL(RXCUI2);",
        "CREATE INDEX IF NOT EXISTS idx_rxnrel_rela ON RXNREL(RELA);",
        "CREATE INDEX IF NOT EXISTS idx_rxnrel_rxcui1_rxcui2 ON RXNREL(RXCUI1, RXCUI2);",
    ]

    with engine.begin() as conn:
        for s in stmts:
            conn.execute(text(s))

# =========================================================
# PRECOMPUTED SAMPLE HELPERS
# =========================================================
def is_precomputed_sample(drug_name):
    if not drug_name:
        return False
    return str(drug_name).strip().lower() in PRECOMPUTED_DRUGS

def get_precomputed_html(drug_name):
    if not drug_name:
        return None

    key = str(drug_name).strip().lower()
    meta = PRECOMPUTED_DRUGS.get(key)

    if not meta:
        return None

    html_path = meta["html_file"]
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")

    return None

# =========================================================
# SEARCH HELPERS
# =========================================================
def extract_name(df):
    if df.empty:
        return df
    df = df.copy()
    df["Product_Name"] = df["STR"].str.extract(r"\[(.*?)\]")
    df["Product_Name"] = df["Product_Name"].fillna("Generic")
    df["Product_Name"] = df["Product_Name"].str.title()
    df = df.drop_duplicates(subset=["Product_Name"])
    return df

def Searchbar(term):
    sql = text("""
        SELECT RXCUI, STR
        FROM RXNCONSO
        WHERE STR LIKE :term
          AND TTY IN ('DP')
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"term": f"%{term}%"})
    return extract_name(df)

def Searchbar_exact_product(term):
    sql = text("""
        SELECT RXCUI, STR
        FROM RXNCONSO
        WHERE UPPER(STR) LIKE UPPER(:term)
          AND TTY = 'DP'
        LIMIT 50
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"term": f"%{term}%"})

    df = extract_name(df)

    if df is None or df.empty:
        return None

    exact_match = df[
        df["Product_Name"].astype(str).str.strip().str.lower()
        == str(term).strip().lower()
    ]

    if not exact_match.empty:
        row = exact_match.iloc[0]
        return {"id": str(row["RXCUI"]), "name": row["Product_Name"]}

    row = df.iloc[0]
    return {"id": str(row["RXCUI"]), "name": row["Product_Name"]}

# =========================================================
# RXNORM DATA HELPERS
# =========================================================
def Exact_drugs(Ing_lst, ID):
    s = ""
    for i, j in enumerate(Ing_lst):
        if i == (len(Ing_lst) - 1):
            s += "r1.RXCUI1 = " + j
        else:
            s += "r1.RXCUI1 = " + j + " or "

    query = f"""
        WITH base AS (
            SELECT r2.RXCUI as ID, r2.STR as DP, r1.RXCUI1 as Ingredient_ID
            FROM RXNREL r1
            JOIN RXNCONSO r2
              ON r1.RXCUI2 = r2.RXCUI
            WHERE ({s}) and r2.TTY = 'DP'
        ),
        keys_all AS (
            SELECT ID
            FROM base
            GROUP by ID
            HAVING COUNT(DISTINCT Ingredient_ID) = {len(Ing_lst)}
        )
        SELECT b.ID, b.DP
        FROM base b
        JOIN keys_all k
          ON b.ID = k.ID
        GROUP BY b.ID, b.DP
    """

    res = pd.read_sql(query, engine)
    dp = res["DP"].astype("string")

    has_bracket = dp.str.contains(r"\[", na=False)

    res["Product_Name"] = np.where(
        has_bracket,
        dp.str.rsplit("[", n=1).str[-1].str.rstrip("]"),
        "Generic"
    )

    keep_mask = (
        has_bracket
        & ~res["Product_Name"].str.lower().duplicated(keep="first")
    )

    res = res.loc[keep_mask].reset_index(drop=True)
    return res

def Union_Drugs(Ing_lst, ID):
    s = ""
    for i, j in enumerate(Ing_lst):
        if i == (len(Ing_lst) - 1):
            s += "r1.RXCUI1 = " + j
        else:
            s += "r1.RXCUI1 = " + j + " or "

    query = f"""
        WITH base AS (
            SELECT r2.RXCUI as ID, r2.STR as DP, r1.RXCUI1 as Ingredient_ID
            FROM RXNREL r1
            JOIN RXNCONSO r2
              ON r1.RXCUI2 = r2.RXCUI
            WHERE ({s}) and r2.TTY = 'DP'
        ),
        keys_all AS (
            SELECT ID
            FROM base
            GROUP by ID
            HAVING COUNT(DISTINCT Ingredient_ID) < {len(Ing_lst)}
        )
        SELECT b.ID, b.DP
        FROM base b
        JOIN keys_all k
          ON b.ID = k.ID
        WHERE b.ID != {ID}
        GROUP BY b.ID, b.DP
    """

    res = pd.read_sql(query, engine)

    dp = res["DP"].astype("string")
    has_bracket = dp.str.contains(r"\[", na=False)

    res["Product_Name"] = np.where(
        has_bracket,
        dp.str.rsplit("[", n=1).str[-1].str.rstrip("]"),
        "Generic"
    )

    res = res.loc[has_bracket].copy()
    res = res.loc[~res["Product_Name"].str.lower().duplicated(keep="first")]
    res = res.drop_duplicates(subset="ID", keep="first").reset_index(drop=True)
    return res

def Ing_count(ID):
    query = f"""
        SELECT count(c.STR) as Count
        FROM RXNCONSO c
        JOIN RXNREL r
          ON c.RXCUI = r.RXCUI2
        WHERE r.RXCUI1 = '{ID}'
          AND c.TTY = 'SCDC';
    """
    df = pd.read_sql(query, engine)
    return int(df["Count"][0])

def Ing_count_bulk(ids):
    if not ids:
        return {}

    ids = [str(i) for i in ids]
    placeholders = ", ".join([f":id{i}" for i in range(len(ids))])
    params = {f"id{i}": ids[i] for i in range(len(ids))}

    sql = text(f"""
        SELECT r.RXCUI1 AS ID, COUNT(DISTINCT c.STR) AS Count
        FROM RXNREL r
        JOIN RXNCONSO c ON c.RXCUI = r.RXCUI2
        WHERE r.RXCUI1 IN ({placeholders})
          AND c.TTY = 'SCDC'
        GROUP BY r.RXCUI1
    """)

    df = pd.read_sql(sql, engine, params=params)
    return dict(zip(df["ID"].astype(str), df["Count"].astype(int)))

def Fetch_Matches(exact_df, union_df, ID):
    target_count = Ing_count(ID)

    unique_ids = exact_df["ID"].dropna().astype(str).unique().tolist()
    count_map = Ing_count_bulk(unique_ids)

    mask = exact_df["ID"].astype(str).map(count_map).eq(target_count)

    union_df = pd.concat([union_df, exact_df.loc[~mask]], ignore_index=True)
    exact_df = exact_df.loc[mask].copy()

    return exact_df, union_df

def Fetch_Ingredients(ID):
    query = text("""
        SELECT r.RXCUI2 as Ingredient_ID, c.STR as Full_Ingredient
        FROM RXNCONSO c
        JOIN RXNREL r ON c.RXCUI = r.RXCUI2
        WHERE r.RXCUI1 = :id AND c.TTY = 'SCDC'
        GROUP BY Ingredient_ID, Full_Ingredient;
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"id": ID})

    parsed_data = []
    for _, row in df.iterrows():
        match = re.search(
            r"(.+?)\s+(\d+(?:\.\d+)?)\s+MG",
            row["Full_Ingredient"],
            re.IGNORECASE
        )
        if match:
            parsed_data.append({
                "Ingredient_ID": row["Ingredient_ID"],
                "Ingredient": match.group(1).strip(),
                "Concentration": float(match.group(2))
            })
        else:
            parsed_data.append({
                "Ingredient_ID": row["Ingredient_ID"],
                "Ingredient": row["Full_Ingredient"],
                "Concentration": 0.0
            })

    return pd.DataFrame(parsed_data)

def Fetch_Dose_Form(ID):
    query = text("""
        SELECT c.STR
        FROM RXNCONSO c
        JOIN RXNREL r ON c.RXCUI = r.RXCUI2
        WHERE r.RXCUI1 = :id AND c.TTY = 'DF'
    """)
    with engine.connect() as conn:
        res = pd.read_sql(query, conn, params={"id": ID})
    return res["STR"].iloc[0] if not res.empty else "Not specified"

def Fetch_Generic_Name(ID):
    query = text("""
        SELECT c.STR
        FROM RXNCONSO c
        JOIN RXNREL r ON c.RXCUI = r.RXCUI2
        WHERE r.RXCUI1 = :id
          AND c.TTY IN ('SCD', 'SCDC', 'SCDF', 'MIN')
    """)
    with engine.connect() as conn:
        res = pd.read_sql(query, conn, params={"id": ID})
    return res["STR"].iloc[0] if not res.empty else "N/A"

def Fetch_Heatmap(df, drug_of_interest_id, drug_of_interest_name):
    searched_row = pd.DataFrame({
        "ID": [str(drug_of_interest_id)],
        "Product_Name": [drug_of_interest_name]
    })

    df_extended = pd.concat(
        [searched_row, df[["ID", "Product_Name"]].copy()],
        ignore_index=True
    )

    df_extended["ID"] = df_extended["ID"].astype(str)

    ids = df_extended["ID"].dropna().unique().tolist()
    if len(ids) == 0:
        return pd.DataFrame(columns=["Product_Name", "ID", "Ingredients_List", "Dose_Form"])

    placeholders = ", ".join([f":id{i}" for i in range(len(ids))])
    params = {f"id{i}": ids[i] for i in range(len(ids))}

    sql_ing = text(f"""
        SELECT
            r.RXCUI1 AS ID,
            c.STR    AS Full_Ingredient
        FROM RXNREL r
        JOIN RXNCONSO c
          ON c.RXCUI = r.RXCUI2
        WHERE r.RXCUI1 IN ({placeholders})
          AND c.TTY = 'SCDC'
    """)

    long_df = pd.read_sql(sql_ing, engine, params=params)

    if long_df.empty:
        out = df_extended.drop_duplicates("Product_Name")[["Product_Name", "ID"]].copy()
        out["Ingredients_List"] = [[] for _ in range(len(out))]
        out["Dose_Form"] = None
        return out.reset_index(drop=True)

    long_df["ID"] = long_df["ID"].astype(str)

    def parse_name_and_mg(full_str):
        full_str = str(full_str)
        match = re.search(r"(.+?)\s+(\d+(?:\.\d+)?)\s+MG\b", full_str, re.IGNORECASE)
        if match:
            return match.group(1).strip(), float(match.group(2))
        return full_str, 0.0

    parsed = long_df["Full_Ingredient"].apply(parse_name_and_mg)
    long_df["Ingredient"] = parsed.apply(lambda t: t[0])
    long_df["Concentration"] = parsed.apply(lambda t: t[1])
    long_df["Concentration"] = pd.to_numeric(long_df["Concentration"], errors="coerce").fillna(0)

    long_df = long_df.merge(df_extended[["ID", "Product_Name"]], on="ID", how="left")

    heatmap_wide = (
        long_df.pivot_table(
            index="Product_Name",
            columns="Ingredient",
            values="Concentration",
            aggfunc="max",
            fill_value=0
        )
        .reset_index()
    )

    ingredient_list_df = (
        long_df.groupby("Product_Name")["Ingredient"]
        .apply(lambda s: sorted(set(s)))
        .reset_index(name="Ingredients_List")
    )

    id_df = (
        df_extended[["Product_Name", "ID"]]
        .drop_duplicates(subset=["Product_Name"], keep="first")
        .reset_index(drop=True)
    )

    heatmap_df = (
        heatmap_wide
        .merge(ingredient_list_df, on="Product_Name", how="left")
        .merge(id_df, on="Product_Name", how="left")
    )

    heatmap_df["Dose_Form"] = None
    return heatmap_df

# =========================================================
# BAR CHARTS
# =========================================================
def Create_Ingredient_Combination_Frequency_Bar(heatmap_df):
    ignore_cols = {"Product_Name", "Ingredients_List", "ID", "Dose_Form"}
    ingredient_cols = [c for c in heatmap_df.columns if c not in ignore_cols]

    if len(ingredient_cols) == 0:
        raise ValueError("No ingredient columns found.")

    binary_df = heatmap_df[ingredient_cols].gt(0)

    combo_series = binary_df.apply(
        lambda row: " + ".join(sorted(row.index[row].tolist())) if row.any() else "No Ingredient",
        axis=1
    )

    combo_freq = combo_series.value_counts().reset_index()
    combo_freq.columns = ["Ingredient_Combination", "Product_Count"]

    chart = alt.Chart(combo_freq).mark_bar().encode(
        x=alt.X("Product_Count:Q", title="Number of Products"),
        y=alt.Y("Ingredient_Combination:N", sort="-x", title="Ingredient Combination"),
        color=alt.Color("Product_Count:Q", scale=alt.Scale(scheme="reds"), title="Frequency"),
        tooltip=[
            alt.Tooltip("Ingredient_Combination:N", title="Combination"),
            alt.Tooltip("Product_Count:Q", title="Products with combination")
        ]
    ).properties(
        width=650,
        height=400,
        title="Ingredient Combination Frequency Across Products"
    )

    return chart

def Create_Ingredient_Frequency_Bar(heatmap_df):
    ignore_cols = {"Product_Name", "Ingredients_List", "ID", "Dose_Form"}
    ingredient_cols = [c for c in heatmap_df.columns if c not in ignore_cols]

    binary_df = heatmap_df[ingredient_cols].gt(0)
    freq_series = binary_df.sum().sort_values(ascending=False)

    freq_df = freq_series.reset_index()
    freq_df.columns = ["Ingredient", "Product_Count"]

    chart = alt.Chart(freq_df).mark_bar().encode(
        x=alt.X("Product_Count:Q", title="Number of Products"),
        y=alt.Y("Ingredient:N", sort="-x", title="Ingredient"),
        color=alt.Color("Product_Count:Q", scale=alt.Scale(scheme="reds"), title="Frequency"),
        tooltip=[
            alt.Tooltip("Ingredient:N"),
            alt.Tooltip("Product_Count:Q", title="Products containing ingredient")
        ]
    ).properties(
        width=650,
        height=400,
        title="Ingredient Frequency Across Products"
    )

    return chart

# =========================================================
# LINKED UMAP + HEATMAP
# =========================================================
def Create_Linked_UMAP_Heatmap(
    heatmap_df,
    drug_of_interest,
    match_by="ID",
    max_related=10,
    doseform_weight=2.0,
    jitter_strength=0.15
):
    if heatmap_df is None:
        raise ValueError("heatmap_df is None")

    if heatmap_df.empty:
        return _message_chart("No data available.")

    df = heatmap_df.copy()
    df = _ensure_product_name(df)
    df = _apply_selection(df, drug_of_interest, match_by)

    if not df["is_selected"].any():
        return _message_chart(f"No match found for {match_by} = {drug_of_interest}.")

    X, ingredient_cols, form_ohe = _build_umap_features(df, doseform_weight=doseform_weight)

    n_samples, n_features = X.shape
    print(
        f"DEBUG LINKED: n_samples={n_samples}, n_features={n_features}, "
        f"ingredient_cols={len(ingredient_cols)}, doseform_cols={form_ohe.shape[1]}"
    )

    try:
        embedding = _fit_umap(X)
    except ValueError as e:
        return _message_chart(str(e), size=16)

    plot_df = _add_embedding_columns(
        df,
        embedding,
        jitter_strength=jitter_strength,
        seed=42
    )

    brushed_source_df = _prepare_brushed_heatmap_input(plot_df)

    value_cols = _get_value_cols(brushed_source_df)
    brush = _build_brush()
    no_brush = "!length(data('brush_store'))"
    has_brush = "length(data('brush_store'))"

    umap_chart = _build_umap_chart(plot_df, brush)

    if not value_cols:
        heatmap_chart = _message_chart("No ingredient data to plot.")
        return (
            alt.hconcat(umap_chart, heatmap_chart)
            .resolve_scale(color="independent")
            .configure_view(fill="white", strokeOpacity=0)
            .configure(background="white")
        )

    heatmap_subset, highlight_title = _make_default_heatmap_subset(
        plot_df,
        max_related=max_related
    )

    df_long_default = _prepare_long_heatmap_df(
        heatmap_subset,
        value_cols=value_cols,
        id_vars=["Product_Name", "ID", "is_selected"]
    )
    default_ingredients = sorted(df_long_default["Ingredient"].unique())
    default_product_order = heatmap_subset["Product_Name"].tolist()
    df_rows_default = _prepare_default_row_bands(heatmap_subset, default_ingredients)

    df_long_brushed = _prepare_long_heatmap_df(
        brushed_source_df,
        value_cols=value_cols,
        id_vars=[
            "Product_Name", "ID", "is_selected",
            "UMAP1_jitter", "UMAP2_jitter", "sort_key"
        ]
    )
    brushed_ingredients = sorted(df_long_brushed["Ingredient"].unique())
    df_rows_brushed = _prepare_brushed_row_bands(brushed_source_df, brushed_ingredients)

    default_layers = _build_default_heatmap_layers(
        df_long_default=df_long_default,
        df_rows_default=df_rows_default,
        default_ingredients=default_ingredients,
        default_product_order=default_product_order,
        no_brush=no_brush
    )

    brushed_layers = _build_brushed_heatmap_layers(
        df_long_brushed=df_long_brushed,
        df_rows_brushed=df_rows_brushed,
        brushed_ingredients=brushed_ingredients,
        brush=brush,
        has_brush=has_brush
    )

    heatmap_chart = (
        default_layers + brushed_layers
    ).properties(
        width=900,
        height=450,
        title=f"Ingredient Concentration Heatmap (Default: {highlight_title} + top {max_related})"
    )

    return (
        alt.hconcat(umap_chart, heatmap_chart)
        .resolve_scale(color="independent")
        .configure_view(fill="white", strokeOpacity=0)
        .configure(background="white")
    )