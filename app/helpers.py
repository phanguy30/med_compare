import dash
import os
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
import re
import altair as alt
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from dash.dependencies import Input, Output, State
from sqlalchemy import bindparam
import numpy as np
import umap

load_dotenv()

host = os.getenv("MYSQL_HOST", "localhost")
port = os.getenv("MYSQL_PORT", "3306")
user = os.getenv("MYSQL_USER","root")
password = os.getenv("MYSQL_PSWD","2316")
db = os.getenv("MYSQL_DB", "rxnorm")

engine = create_engine(
    f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4"
)


def Exact_drugs(Ing_lst,ID):
    s = ""
    for i,j in enumerate(Ing_lst):
        if i == (len(Ing_lst) - 1):
            s+="r1.RXCUI1 = "+j
        else:
            s+="r1.RXCUI1 = "+j+" or "
            
    query = f"""
    WITH base AS (
        SELECT r2.RXCUI as ID, r2.STR as DP, r1.RXCUI1 as Ingredient_ID
        FROM RXNREL r1
        JOIN RXNCONSO r2
        ON r1.RXCUI2 = r2.RXCUI
        WHERE ({s}) and r2.TTY = "DP"
    ),
    keys_all AS (
        SELECT ID
        FROM base
        GROUP by ID
        HAVING COUNT(DISTINCT Ingredient_ID) = {len(Ing_lst)}
    )
    SELECT b.ID,b.DP
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

def Union_Drugs(Ing_lst,ID):
    s = ""
    for i,j in enumerate(Ing_lst):
        if i == (len(Ing_lst) - 1):
            s+="r1.RXCUI1 = "+j
        else:
            s+="r1.RXCUI1 = "+j+" or "
            
    query = f"""
    WITH base AS (
        SELECT r2.RXCUI as ID, r2.STR as DP, r1.RXCUI1 as Ingredient_ID
        FROM RXNREL r1
        JOIN RXNCONSO r2
        ON r1.RXCUI2 = r2.RXCUI
        WHERE ({s}) and r2.TTY = "DP"
    ),
    keys_all AS (
        SELECT ID
        FROM base
        GROUP by ID
        HAVING COUNT(DISTINCT Ingredient_ID) < {len(Ing_lst)}
    )
    SELECT b.ID,b.DP
    FROM base b
    JOIN keys_all k
    ON b.ID = k.ID
    WHERE b.Id != {ID}
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
    WHERE r.RXCUI1 = "{ID}"
      AND c.TTY = "SCDC";
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
    count_map = Ing_count_bulk(unique_ids)   # ✅ 1 query

    mask = exact_df["ID"].astype(str).map(count_map).eq(target_count)

    union_df = pd.concat([union_df, exact_df.loc[~mask]], ignore_index=True)
    exact_df = exact_df.loc[mask].copy()

    return exact_df, union_df

def extract_name(df):
    if df.empty:
        return df
    df["Product_Name"] = df["STR"].str.extract(r'\[(.*?)\]')
    df["Product_Name"] = df["Product_Name"].fillna("Generic")
    df["Product_Name"] = df["Product_Name"].str.title()
    df = df.drop_duplicates(subset=["Product_Name"])
    return df

def Searchbar(term):
    sql = text("SELECT RXCUI, STR FROM RXNCONSO WHERE STR LIKE :term AND TTY IN ('DP')")
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={'term': f'%{term}%'})
    return extract_name(df)

def Fetch_Ingredients(ID):
    query = text("""
        SELECT r.RXCUI2 as Ingredient_ID, c.STR as Full_Ingredient
        FROM RXNCONSO c
        JOIN RXNREL r ON c.RXCUI = r.RXCUI2
        WHERE r.RXCUI1 = :id AND c.TTY = "SCDC"
        GROUP BY Ingredient_ID, Full_Ingredient;
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"id": ID})
    
    parsed_data = []
    for _, row in df.iterrows():
        match = re.search(r"(.+?)\s+(\d+(?:\.\d+)?)\s+MG", row["Full_Ingredient"], re.IGNORECASE)
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
    query = text("SELECT c.STR FROM RXNCONSO c JOIN RXNREL r ON c.RXCUI = r.RXCUI2 WHERE r.RXCUI1 = :id AND c.TTY = 'DF'")
    with engine.connect() as conn:
        res = pd.read_sql(query, conn, params={'id': ID})
    return res["STR"].iloc[0] if not res.empty else "Not specified"

def Fetch_Generic_Name(ID):
    query = text("SELECT c.STR FROM RXNCONSO c JOIN RXNREL r ON c.RXCUI = r.RXCUI2 WHERE r.RXCUI1 = :id AND c.TTY IN ('SCD', 'SCDC', 'SCDF', 'MIN')")
    with engine.connect() as conn:
        res = pd.read_sql(query, conn, params={'id': ID})
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

    # ensure string IDs
    df_extended["ID"] = df_extended["ID"].astype(str)

    # ---- 1) Get all ingredient rows in ONE query ----
    ids = df_extended["ID"].dropna().unique().tolist()
    if len(ids) == 0:
        return pd.DataFrame(columns=["Product_Name", "ID", "Ingredients_List", "Dose_Form"])

    placeholders = ", ".join([f":id{i}" for i in range(len(ids))])
    params = {f"id{i}": ids[i] for i in range(len(ids))}

    sql_ing = text(f"""
        SELECT
            r.RXCUI1 AS ID,
            c.STR    AS Ingredient,
            -- If you have a concentration column elsewhere, join it here.
            -- For now, keep a placeholder concentration = 1 if present, else 0 won't appear anyway.
            1.0 AS Concentration
        FROM RXNREL r
        JOIN RXNCONSO c
            ON c.RXCUI = r.RXCUI2
        WHERE r.RXCUI1 IN ({placeholders})
          AND c.TTY = 'SCDC'
    """)

    long_df = pd.read_sql(sql_ing, engine, params=params)

    # If you truly have concentrations, replace the query above to bring the real concentration.
    # Then keep this numeric cleanup:
    long_df["Concentration"] = pd.to_numeric(long_df["Concentration"], errors="coerce").fillna(0)

    if long_df.empty:
        out = df_extended.drop_duplicates("Product_Name")[["Product_Name", "ID"]].copy()
        out["Ingredients_List"] = [[] for _ in range(len(out))]
        out["Dose_Form"] = None
        return out.reset_index(drop=True)

    # Add Product_Name by merging
    long_df = long_df.merge(df_extended[["ID", "Product_Name"]], on="ID", how="left")

    # ---- 2) Pivot ----
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

    # ingredient list
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

    # ---- 3) OPTIONAL: Dose_Form in ONE query ----
    # Only do this if you really need it for UMAP / tooltips.
    # If Dose_Form() is also doing DB work, do a bulk fetch here similarly.

    heatmap_df["Dose_Form"] = None  # placeholder; fill via bulk query if needed

    return heatmap_df

def Create_Altair_Heatmap(heatmap_df, drug_of_interest_name):
    if "Product_Name" not in heatmap_df.columns:
        heatmap_df = heatmap_df.reset_index()

    num_products = heatmap_df["Product_Name"].nunique()
    height_per_product = 20
    dynamic_height = max(250, min(1400, num_products * height_per_product))

    non_ingredient_cols = {"Product_Name", "Ingredients_List", "ID", "Dose_Form"}
    value_cols = [c for c in heatmap_df.columns if c not in non_ingredient_cols]

    df_long = heatmap_df.melt(
        id_vars=["Product_Name"],
        value_vars=value_cols,
        var_name="Ingredient",
        value_name="Concentration"
    )

    df_long["Product_Name"] = df_long["Product_Name"].astype(str)
    df_long["Ingredient"] = df_long["Ingredient"].astype(str)
    df_long["Concentration"] = pd.to_numeric(df_long["Concentration"], errors="coerce").fillna(0)

    df_long["Relative_Conc"] = (
        df_long.groupby("Ingredient")["Concentration"]
        .transform(lambda x: x / x.max() if x.max() != 0 else 0)
    )

    ingredients = sorted(df_long["Ingredient"].unique())
    if len(ingredients) == 0:
        return alt.Chart(pd.DataFrame({"msg": ["No data to plot."]})).mark_text().encode(text="msg:N")

    first_ing = ingredients[0]
    last_ing = ingredients[-1]

    df_rows = (
        df_long[["Product_Name"]]
        .drop_duplicates()
        .sort_values("Product_Name")
        .reset_index(drop=True)
    )
    df_rows["row_index"] = df_rows.index
    df_rows["is_odd"] = (df_rows["row_index"] % 2 == 1)
    df_rows["x_start"] = first_ing
    df_rows["x_end"] = last_ing

    # Shared encodings
    base = alt.Chart(df_long).encode(
    x=alt.X(
        "Ingredient:N",
        axis=alt.Axis(labelAngle=-45),
        sort=ingredients,
        scale=alt.Scale(padding=0) 
    ),
    y=alt.Y("Product_Name:N", sort='-x')
)

    row_bands = alt.Chart(df_rows).mark_rect().encode(
    x=alt.X(
        "x_start:N",
        sort=ingredients,
        scale=alt.Scale(padding=0), 
        title=None
    ),
    x2="x_end:N",
    y=alt.Y("Product_Name:N", sort='-x'),
    color=alt.condition(
        alt.datum.is_odd,
        alt.value("#efe7f6"),
        alt.value("#f6f3ef")
    )
)
    # 1) Highlight zero cells ONLY for drug_of_interest row
    highlight_zeros = base.transform_filter(
        (alt.datum.Product_Name == str(drug_of_interest_name)) &
        (alt.datum.Concentration == 0)
    ).mark_rect().encode(
        color=alt.value("#f3d7d7")
    )

    # 2) Main heatmap: non-zero cells only
    nonzero_layer = base.transform_filter(
        alt.datum.Concentration > 0
    ).mark_rect().encode(
        color=alt.Color(
            "Relative_Conc:Q",
            scale=alt.Scale(scheme="reds", domain=[0, 1]),
            title="Relative Concentration"
        ),
        tooltip=[
            "Product_Name:N",
            "Ingredient:N",
            alt.Tooltip("Concentration:Q", title="Concentration (mg)"),
            alt.Tooltip("Relative_Conc:Q", format=".2f", title="Relative")
        ]
    )

    chart = (row_bands + highlight_zeros + nonzero_layer).properties(
    width= 1300,
    height=dynamic_height,
    title=f"Ingredient Concentration Heatmap (zebra rows + 0-cells highlighted for: {drug_of_interest_name})"
    ).configure_view(
        fill="white",          # change here
        strokeOpacity=0
    ).configure(
        background="white"     # change here
    )

    return chart

def Create_UMAP_Cluster(heatmap_df, drug_of_interest_name, doseform_weight=2.0, jitter_strength=0.15):

    # ---- 0) Hard checks ----
    if heatmap_df is None:
        raise ValueError("heatmap_df is None")
    if heatmap_df.empty:
        raise ValueError("heatmap_df is EMPTY (0 rows). UMAP can't run.")

    ignore_cols = {"Product_Name", "Ingredients_List", "ID", "Dose_Form"}
    ingredient_cols = [c for c in heatmap_df.columns if c not in ignore_cols]

    # Dose form one-hot
    df_form = heatmap_df[["Dose_Form"]].copy()
    df_form["Dose_Form"] = df_form["Dose_Form"].fillna("UNKNOWN").astype(str)
    form_ohe = pd.get_dummies(df_form["Dose_Form"], prefix="DF").astype(float) * float(doseform_weight)

    # Ingredient features
    if len(ingredient_cols) > 0:
        X_ing = (
            heatmap_df[ingredient_cols]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
            .to_numpy(dtype=float)
        )
    else:
        # No ingredient columns → (n,0)
        X_ing = np.zeros((len(heatmap_df), 0), dtype=float)

    # Combine
    X = np.hstack([X_ing, form_ohe.to_numpy(dtype=float)])

    # Diagnostics (super important)
    n_samples, n_features = X.shape
    print(f"DEBUG: n_samples={n_samples}, n_features={n_features}, ingredient_cols={len(ingredient_cols)}, doseform_cols={form_ohe.shape[1]}")
    print("DEBUG: unique products =", heatmap_df["Product_Name"].nunique())

    # If you end up with 0 rows or only 1 row, UMAP will fail
    if n_samples < 2:
        raise ValueError(f"UMAP needs at least 2 rows. You have {n_samples}. Your heatmap_df likely contains only '{drug_of_interest_name}'.")

    # UMAP requires n_neighbors < n_samples
    n_neighbors = min(10, n_samples - 1)
    n_neighbors = max(2, n_neighbors)

    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=0.3,
        n_components=2,
        metric="euclidean",
        random_state=42
    )
    embedding = reducer.fit_transform(X)

    plot_df = heatmap_df[["Product_Name", "Ingredients_List", "Dose_Form"]].copy()
    plot_df["UMAP1"] = embedding[:, 0]
    plot_df["UMAP2"] = embedding[:, 1]

    plot_df["Ingredients_Str"] = plot_df["Ingredients_List"].apply(
        lambda x: ", ".join(x) if isinstance(x, list) else str(x)
    )

    plot_df["Is_Interest"] = plot_df["Product_Name"].astype(str).str.lower().eq(str(drug_of_interest_name).lower())

    rng = np.random.default_rng(42)
    plot_df["UMAP1_jitter"] = plot_df["UMAP1"] + rng.normal(0, jitter_strength, len(plot_df))
    plot_df["UMAP2_jitter"] = plot_df["UMAP2"] + rng.normal(0, jitter_strength, len(plot_df))

    chart = alt.Chart(plot_df).mark_circle(size=100).encode(
        x=alt.X("UMAP1_jitter:Q", title="UMAP Dimension 1"),
        y=alt.Y("UMAP2_jitter:Q", title="UMAP Dimension 2"),
        color=alt.condition(alt.datum.Is_Interest, alt.value("red"), alt.value("steelblue")),
        size=alt.condition(alt.datum.Is_Interest, alt.value(220), alt.value(80)),
        tooltip=[
            alt.Tooltip("Product_Name:N", title="Product"),
            alt.Tooltip("Dose_Form:N", title="Dose Form"),
            alt.Tooltip("Ingredients_Str:N", title="Ingredients")
        ]
    ).properties(
        width=650,
        height=400,
        title=f"Drug Similarity Clustering (UMAP) — DoseForm weighted x{doseform_weight}"
    )

    return chart

def Create_Ingredient_Frequency_Bar(heatmap_df):

    # Identify ingredient columns
    ignore_cols = {"Product_Name", "Ingredients_List", "ID", "Dose_Form"}
    ingredient_cols = [c for c in heatmap_df.columns if c not in ignore_cols]

    # Convert to binary presence matrix
    binary_df = heatmap_df[ingredient_cols].gt(0)

    # Count frequency
    freq_series = binary_df.sum().sort_values(ascending=False)

    # Convert to dataframe
    freq_df = freq_series.reset_index()
    freq_df.columns = ["Ingredient", "Product_Count"]

    # Create bar chart
    chart = alt.Chart(freq_df).mark_bar().encode(

        x=alt.X(
            "Product_Count:Q",
            title="Number of Products"
        ),

        y=alt.Y(
            "Ingredient:N",
            sort='-x',
            title="Ingredient"
        ),

        color=alt.Color(
            "Product_Count:Q",
            scale=alt.Scale(scheme="reds"),
            title="Frequency"
        ),

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