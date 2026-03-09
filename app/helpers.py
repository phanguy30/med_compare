import os




import dash
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
import re
import altair as alt
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from dash.dependencies import Input, Output, State
import numpy as np
import umap
from difflib import get_close_matches




# SQLite Engine
engine = create_engine(
    "sqlite:///rxnorm.sqlite",
    connect_args={"check_same_thread": False},  # important for web servers (gunicorn threads)
)


# One-time: create indexes
# Call this once at app startup.
def ensure_sqlite_indexes():
    stmts = [
        # RXNCONSO
        "CREATE INDEX IF NOT EXISTS idx_rxnconso_str ON RXNCONSO(STR);",
        "CREATE INDEX IF NOT EXISTS idx_rxnconso_rxcui ON RXNCONSO(RXCUI);",
        "CREATE INDEX IF NOT EXISTS idx_rxnconso_tty ON RXNCONSO(TTY);",
        "CREATE INDEX IF NOT EXISTS idx_rxnconso_tty_rxcui ON RXNCONSO(TTY, RXCUI);",


        # RXNREL
        "CREATE INDEX IF NOT EXISTS idx_rxnrel_rxcui1 ON RXNREL(RXCUI1);",
        "CREATE INDEX IF NOT EXISTS idx_rxnrel_rxcui2 ON RXNREL(RXCUI2);",
        "CREATE INDEX IF NOT EXISTS idx_rxnrel_rela ON RXNREL(RELA);",
        "CREATE INDEX IF NOT EXISTS idx_rxnrel_rxcui1_rxcui2 ON RXNREL(RXCUI1, RXCUI2);",
    ]

    with engine.begin() as conn:
        for s in stmts:
            conn.execute(text(s))

def Exact_drugs(Ing_lst,ID):
    s = ''
    for i,j in enumerate(Ing_lst):
        if i == (len(Ing_lst) - 1):
            s+='r1.RXCUI1 = '+j
        else:
            s+='r1.RXCUI1 = '+j+' or '
            
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
    SELECT b.ID,b.DP
    FROM base b
    JOIN keys_all k
    ON b.ID = k.ID
    GROUP BY b.ID, b.DP
    """
    
    res = pd.read_sql(query, engine)
    dp = res['DP'].astype('string')

    has_bracket = dp.str.contains(r'\[', na=False)
    
    res['Product_Name'] = np.where(
        has_bracket,
        dp.str.rsplit('[', n=1).str[-1].str.rstrip(']'),
        'Generic'
    )
    
    keep_mask = (
        has_bracket
        & ~res['Product_Name'].str.lower().duplicated(keep='first')
    )
    
    res = res.loc[keep_mask].reset_index(drop=True)
    return res

def Union_Drugs(Ing_lst,ID):
    s = ""
    for i,j in enumerate(Ing_lst):
        if i == (len(Ing_lst) - 1):
            s+='r1.RXCUI1 = '+j
        else:
            s+='r1.RXCUI1 = '+j+' or '
            
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
    SELECT b.ID,b.DP
    FROM base b
    JOIN keys_all k
    ON b.ID = k.ID
    WHERE b.Id != {ID}
    GROUP BY b.ID, b.DP
    """
    
    res = pd.read_sql(query, engine)

    dp = res['DP'].astype('string')
    has_bracket = dp.str.contains(r'\[', na=False)
    res['Product_Name'] = np.where(
        has_bracket,
        dp.str.rsplit('[', n=1).str[-1].str.rstrip(']'),
        'Generic'
    )
    
    res = res.loc[has_bracket].copy()
    res = res.loc[~res['Product_Name'].str.lower().duplicated(keep='first')]
    res = res.drop_duplicates(subset='ID', keep='first').reset_index(drop=True)
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
    return int(df['Count'][0])

def Ing_count_bulk(ids):
    if not ids:
        return {}

    ids = [str(i) for i in ids]
    placeholders = ', '.join([f':id{i}' for i in range(len(ids))])
    params = {f'id{i}': ids[i] for i in range(len(ids))}

    sql = text(f"""
        SELECT r.RXCUI1 AS ID, COUNT(DISTINCT c.STR) AS Count
        FROM RXNREL r
        JOIN RXNCONSO c ON c.RXCUI = r.RXCUI2
        WHERE r.RXCUI1 IN ({placeholders})
          AND c.TTY = 'SCDC'
        GROUP BY r.RXCUI1
    """)

    df = pd.read_sql(sql, engine, params=params)
    return dict(zip(df['ID'].astype(str), df['Count'].astype(int)))

def Fetch_Matches(exact_df, union_df, ID):
    target_count = Ing_count(ID)

    unique_ids = exact_df['ID'].dropna().astype(str).unique().tolist()
    count_map = Ing_count_bulk(unique_ids)   

    mask = exact_df['ID'].astype(str).map(count_map).eq(target_count)

    union_df = pd.concat([union_df, exact_df.loc[~mask]], ignore_index=True)
    exact_df = exact_df.loc[mask].copy()

    return exact_df, union_df

def extract_name(df):
    if df.empty:
        return df
    df['Product_Name'] = df['STR'].str.extract(r'\[(.*?)\]')
    df['Product_Name'] = df['Product_Name'].fillna('Generic')
    df['Product_Name'] = df['Product_Name'].str.title()
    df = df.drop_duplicates(subset=['Product_Name'])
    return df

def Searchbar(term):
    sql = text("""
        SELECT RXCUI, STR FROM RXNCONSO WHERE STR LIKE :term AND TTY IN ('DP')
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={'term': f'%{term}%'})
    return extract_name(df)

def Fetch_Ingredients(ID):
    query = text("""
        SELECT r.RXCUI2 as Ingredient_ID, c.STR as Full_Ingredient
        FROM RXNCONSO c
        JOIN RXNREL r ON c.RXCUI = r.RXCUI2
        WHERE r.RXCUI1 = :id AND c.TTY = 'SCDC'
        GROUP BY Ingredient_ID, Full_Ingredient;
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={'id': ID})
    
    parsed_data = []
    for _, row in df.iterrows():
        match = re.search(r'(.+?)\s+(\d+(?:\.\d+)?)\s+MG', row['Full_Ingredient'], re.IGNORECASE)
        if match:
            parsed_data.append({
                'Ingredient_ID': row['Ingredient_ID'],
                'Ingredient': match.group(1).strip(),
                'Concentration': float(match.group(2)) 
            })
        else:
            parsed_data.append({
                'Ingredient_ID': row['Ingredient_ID'],
                'Ingredient': row['Full_Ingredient'],
                'Concentration': 0.0 
            })
    return pd.DataFrame(parsed_data)

def Fetch_Dose_Form(ID):
    query = text("""
        SELECT c.STR FROM RXNCONSO c JOIN RXNREL r ON c.RXCUI = r.RXCUI2 WHERE r.RXCUI1 = :id AND c.TTY = 'DF'
    """)
    with engine.connect() as conn:
        res = pd.read_sql(query, conn, params={'id': ID})
    return res['STR'].iloc[0] if not res.empty else 'Not specified'

def Fetch_Generic_Name(ID):
    query = text("""
        SELECT c.STR FROM RXNCONSO c JOIN RXNREL r ON c.RXCUI = r.RXCUI2 WHERE r.RXCUI1 = :id AND c.TTY IN ('SCD', 'SCDC', 'SCDF', 'MIN')
    """)
    with engine.connect() as conn:
        res = pd.read_sql(query, conn, params={'id': ID})
    return res['STR'].iloc[0] if not res.empty else 'N/A'


def Fetch_Heatmap(df, drug_of_interest_id, drug_of_interest_name):

    searched_row = pd.DataFrame({
        'ID': [str(drug_of_interest_id)],
        'Product_Name': [drug_of_interest_name]
    })

    df_extended = pd.concat(
        [searched_row, df[['ID', 'Product_Name']].copy()],
        ignore_index=True
    )

    # ensure string IDs
    df_extended['ID'] = df_extended['ID'].astype(str)

    # ---- 1) Get all ingredient rows in ONE query ----
    ids = df_extended['ID'].dropna().unique().tolist()
    if len(ids) == 0:
        return pd.DataFrame(columns=['Product_Name', 'ID', 'Ingredients_List', 'Dose_Form'])

    placeholders = ', '.join([f':id{i}' for i in range(len(ids))])
    params = {f'id{i}': ids[i] for i in range(len(ids))}

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
        out = df_extended.drop_duplicates('Product_Name')[['Product_Name', 'ID']].copy()
        out['Ingredients_List'] = [[] for _ in range(len(out))]
        out['Dose_Form'] = None
        return out.reset_index(drop=True)

    # ensure ID is string for merge
    long_df['ID'] = long_df['ID'].astype(str)

    # ---- 2) Parse 'name + MG' into Ingredient + Concentration ----
    def parse_name_and_mg(full_str):
        full_str = str(full_str)
        match = re.search(r'(.+?)\s+(\d+(?:\.\d+)?)\s+MG\b', full_str, re.IGNORECASE)
        if match:
            return match.group(1).strip(), float(match.group(2))
        return full_str, 0.0

    parsed = long_df['Full_Ingredient'].apply(parse_name_and_mg)
    long_df['Ingredient'] = parsed.apply(lambda t: t[0])
    long_df['Concentration'] = parsed.apply(lambda t: t[1])

    long_df['Concentration'] = pd.to_numeric(long_df['Concentration'], errors='coerce').fillna(0)

    # ---- 3) Add Product_Name by merging ----
    long_df = long_df.merge(df_extended[['ID', 'Product_Name']], on='ID', how='left')

    # ---- 4) Pivot wide for heatmap ----
    heatmap_wide = (
        long_df.pivot_table(
            index='Product_Name',
            columns='Ingredient',
            values='Concentration',
            aggfunc='max',
            fill_value=0
        )
        .reset_index()
    )

    # ingredient list
    ingredient_list_df = (
        long_df.groupby('Product_Name')['Ingredient']
        .apply(lambda s: sorted(set(s)))
        .reset_index(name='Ingredients_List')
    )

    id_df = (
        df_extended[['Product_Name', 'ID']]
        .drop_duplicates(subset=['Product_Name'], keep='first')
        .reset_index(drop=True)
    )

    heatmap_df = (
        heatmap_wide
        .merge(ingredient_list_df, on='Product_Name', how='left')
        .merge(id_df, on='Product_Name', how='left')
    )

    heatmap_df['Dose_Form'] = None
    return heatmap_df


def Build_UMAP_Data(heatmap_df, drug_of_interest_id=None, doseform_weight=2.0, jitter_strength=0.15):
    if heatmap_df is None:
        raise ValueError("heatmap_df is None")
    if heatmap_df.empty:
        raise ValueError("heatmap_df is EMPTY (0 rows). UMAP can't run.")

    df = heatmap_df.copy()

    ignore_cols = {'Product_Name', 'Ingredients_List', 'ID', 'Dose_Form'}
    ingredient_cols = [c for c in df.columns if c not in ignore_cols]

    df_form = df[['Dose_Form']].copy()
    df_form['Dose_Form'] = df_form['Dose_Form'].fillna('UNKNOWN').astype(str)

    form_ohe = (
        pd.get_dummies(df_form['Dose_Form'], prefix='DF')
        .astype(np.float32) * np.float32(doseform_weight)
    )

    if len(ingredient_cols) > 0:
        X_ing = (
            df[ingredient_cols]
            .apply(pd.to_numeric, errors='coerce')
            .fillna(0)
            .to_numpy(dtype=np.float32)
        )
    else:
        X_ing = np.zeros((len(df), 0), dtype=np.float32)

    X = np.hstack([X_ing, form_ohe.to_numpy(dtype=np.float32)])
    X = np.ascontiguousarray(X, dtype=np.float32)

    n_samples, n_features = X.shape
    print(f"DEBUG: n_samples={n_samples}, n_features={n_features}, ingredient_cols={len(ingredient_cols)}, doseform_cols={form_ohe.shape[1]}")

    if n_samples < 3:
        out = df[['ID', 'Product_Name', 'Ingredients_List', 'Dose_Form']].copy()
        out['UMAP1'] = 0
        out['UMAP2'] = 0
        out['Is_Interest'] = out['ID'].astype(str).eq(str(drug_of_interest_id))
        return out

    n_neighbors = min(10, n_samples - 1)
    n_neighbors = max(2, n_neighbors)

    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=0.3,
        n_components=2,
        metric='euclidean',
        random_state=42,
        low_memory=True,
        n_jobs=1
    )

    embedding = reducer.fit_transform(X)

    out = df.copy()
    out['UMAP1'] = embedding[:, 0]
    out['UMAP2'] = embedding[:, 1]

    rng = np.random.default_rng(42)
    out['UMAP1_jitter'] = out['UMAP1'] + rng.normal(0, jitter_strength, len(out))
    out['UMAP2_jitter'] = out['UMAP2'] + rng.normal(0, jitter_strength, len(out))

    out['Ingredients_Str'] = out['Ingredients_List'].apply(
        lambda x: ', '.join(x) if isinstance(x, list) else str(x)
    )
    out['Is_Interest'] = out['ID'].astype(str).eq(str(drug_of_interest_id))

    return out

def Create_Interactive_UMAP_Heatmap(heatmap_df, drug_of_interest_id=None, doseform_weight=2.0):
    plot_df = Build_UMAP_Data(
        heatmap_df=heatmap_df,
        drug_of_interest_id=drug_of_interest_id,
        doseform_weight=doseform_weight,
        jitter_strength=0.15
    )

    if plot_df.empty:
        return alt.Chart(pd.DataFrame({'msg': ['No data available.']})).mark_text(size=14).encode(text='msg:N')

    non_ingredient_cols = {
        'Product_Name', 'Ingredients_List', 'ID', 'Dose_Form',
        'UMAP1', 'UMAP2', 'UMAP1_jitter', 'UMAP2_jitter',
        'Ingredients_Str', 'Is_Interest'
    }
    ingredient_cols = [c for c in plot_df.columns if c not in non_ingredient_cols]

    if len(ingredient_cols) == 0:
        return alt.Chart(pd.DataFrame({'msg': ['No ingredient data to plot.']})).mark_text(size=14).encode(text='msg:N')

    # selection: click point on UMAP
    point_select = alt.selection_point(
        fields=['ID'],
        empty='all',
        on='click',
        clear='dblclick'
    )

    # zoom/pan for UMAP
    zoom = alt.selection_interval(bind='scales')

    # ----------------------------
    # UMAP chart
    # ----------------------------
    base_points = alt.Chart(plot_df).mark_circle(
        size=90,
        color='steelblue',
        opacity=0.8
    ).encode(
        x=alt.X('UMAP1_jitter:Q', title='UMAP Dimension 1'),
        y=alt.Y('UMAP2_jitter:Q', title='UMAP Dimension 2'),
        tooltip=[
            alt.Tooltip('Product_Name:N', title='Product'),
            alt.Tooltip('ID:N', title='ID'),
            alt.Tooltip('Dose_Form:N', title='Dose Form'),
            alt.Tooltip('Ingredients_Str:N', title='Ingredients')
        ]
    )

    interest_points = alt.Chart(plot_df).transform_filter(
        alt.datum.Is_Interest
    ).mark_circle(
        size=180,
        color='orange',
        opacity=0.95
    ).encode(
        x='UMAP1_jitter:Q',
        y='UMAP2_jitter:Q',
        tooltip=[
            alt.Tooltip('Product_Name:N', title='Product'),
            alt.Tooltip('ID:N', title='ID'),
            alt.Tooltip('Dose_Form:N', title='Dose Form'),
            alt.Tooltip('Ingredients_Str:N', title='Ingredients')
        ]
    )

    selected_points = alt.Chart(plot_df).transform_filter(
        point_select
    ).mark_circle(
        size=260,
        color='red',
        opacity=1.0
    ).encode(
        x='UMAP1_jitter:Q',
        y='UMAP2_jitter:Q',
        tooltip=[
            alt.Tooltip('Product_Name:N', title='Product'),
            alt.Tooltip('ID:N', title='ID'),
            alt.Tooltip('Dose_Form:N', title='Dose Form'),
            alt.Tooltip('Ingredients_Str:N', title='Ingredients')
        ]
    )

    umap_chart = (
        (base_points + interest_points + selected_points)
        .add_params(point_select, zoom)
        .properties(
            width=500,
            height=400,
            title=f'Drug Similarity Clustering (UMAP) — DoseForm weighted x{doseform_weight}'
        )
    )

    # ----------------------------
    # Heatmap long format
    # ----------------------------
    df_long = plot_df.melt(
        id_vars=['Product_Name', 'ID', 'Is_Interest'],
        value_vars=ingredient_cols,
        var_name='Ingredient',
        value_name='Concentration'
    )

    df_long['Concentration'] = pd.to_numeric(df_long['Concentration'], errors='coerce').fillna(0)

    df_long['Relative_Conc'] = (
        df_long.groupby('Ingredient')['Concentration']
        .transform(lambda x: x / x.max() if x.max() != 0 else 0)
    )

    product_order = plot_df['Product_Name'].tolist()

    heatmap = (
        alt.Chart(df_long)
        .transform_filter(point_select)
        .mark_rect()
        .encode(
            x=alt.X('Ingredient:N', axis=alt.Axis(labelAngle=-45)),
            y=alt.Y('Product_Name:N', sort=product_order),
            color=alt.Color(
                'Relative_Conc:Q',
                scale=alt.Scale(scheme='reds', domain=[0, 1]),
                title='Relative Concentration'
            ),
            tooltip=[
                alt.Tooltip('Product_Name:N', title='Product'),
                alt.Tooltip('ID:N', title='ID'),
                alt.Tooltip('Ingredient:N', title='Ingredient'),
                alt.Tooltip('Concentration:Q', title='Concentration (mg)'),
                alt.Tooltip('Relative_Conc:Q', title='Relative', format='.2f')
            ]
        )
        .properties(
            width=800,
            height=400,
            title='Ingredient Concentration Heatmap (click point on UMAP)'
        )
    )

    text_layer = (
        alt.Chart(df_long)
        .transform_filter(point_select)
        .transform_filter(alt.datum.Concentration > 0)
        .mark_text(fontSize=10)
        .encode(
            x='Ingredient:N',
            y=alt.Y('Product_Name:N', sort=product_order),
            text=alt.Text('Concentration:Q', format='.0f'),
            color=alt.value('black')
        )
    )

    return alt.hconcat(
        umap_chart,
        heatmap + text_layer
    ).resolve_scale(
        color='independent'
    )


def Create_Ingredient_Frequency_Bar(heatmap_df):

    # Identify ingredient columns
    ignore_cols = {'Product_Name', 'Ingredients_List', 'ID', 'Dose_Form'}
    ingredient_cols = [c for c in heatmap_df.columns if c not in ignore_cols]

    # Convert to binary presence matrix
    binary_df = heatmap_df[ingredient_cols].gt(0)

    # Count frequency
    freq_series = binary_df.sum().sort_values(ascending=False)

    # Convert to dataframe
    freq_df = freq_series.reset_index()
    freq_df.columns = ['Ingredient', 'Product_Count']

    # Create bar chart
    chart = alt.Chart(freq_df).mark_bar().encode(

        x=alt.X(
            'Product_Count:Q',
            title='Number of Products'
        ),

        y=alt.Y(
            'Ingredient:N',
            sort='-x',
            title='Ingredient'
        ),

        color=alt.Color(
            'Product_Count:Q',
            scale=alt.Scale(scheme='reds'),
            title='Frequency'
        ),

        tooltip=[
            alt.Tooltip('Ingredient:N'),
            alt.Tooltip('Product_Count:Q', title='Products containing ingredient')
        ]

    ).properties(
        width=650,
        height=400,
        title='Ingredient Frequency Across Products'
    )
    return chart



def Create_Ingredient_Combination_Frequency_Bar(heatmap_df):

    # Identify ingredient columns
    ignore_cols = {'Product_Name', 'Ingredients_List', 'ID', 'Dose_Form'}
    ingredient_cols = [c for c in heatmap_df.columns if c not in ignore_cols]

    if len(ingredient_cols) == 0:
        raise ValueError("No ingredient columns found.")

    # Convert to binary presence matrix
    binary_df = heatmap_df[ingredient_cols].gt(0)

    # Build a canonical combination label for each product
    combo_series = binary_df.apply(
        lambda row: " + ".join(sorted(row.index[row].tolist())) if row.any() else "No Ingredient",
        axis=1
    )

    # Count frequency of each combination
    combo_freq = combo_series.value_counts().reset_index()
    combo_freq.columns = ['Ingredient_Combination', 'Product_Count']

    # Create bar chart
    chart = alt.Chart(combo_freq).mark_bar().encode(
        x=alt.X(
            'Product_Count:Q',
            title='Number of Products'
        ),
        y=alt.Y(
            'Ingredient_Combination:N',
            sort='-x',
            title='Ingredient Combination'
        ),
        color=alt.Color(
            'Product_Count:Q',
            scale=alt.Scale(scheme='reds'),
            title='Frequency'
        ),
        tooltip=[
            alt.Tooltip('Ingredient_Combination:N', title='Combination'),
            alt.Tooltip('Product_Count:Q', title='Products with combination')
        ]
    ).properties(
        width=650,
        height=400,
        title='Ingredient Combination Frequency Across Products'
    )

    return chart



