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

def Fetch_Matches(exact_df, union_df, ID):
    target_count = Ing_count(ID)

    unique_ids = exact_df["ID"].dropna().unique()
    count_map = {uid: Ing_count(uid) for uid in unique_ids}

    mask = exact_df["ID"].map(count_map).eq(target_count)

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
        "ID": [drug_of_interest_id],
        "Product_Name": [drug_of_interest_name]
    })
    df_extended = pd.concat([searched_row, df], ignore_index=True)
    
    rows = []
    for _, row in df_extended.iterrows():
        ingredients = Fetch_Ingredients(row["ID"])
        for _, ing in ingredients.iterrows():
            rows.append({
                "ID": row["ID"], 
                "Product_Name": row["Product_Name"],
                "Ingredient": ing["Ingredient"],
                "Concentration": ing["Concentration"]
            })

    long_df = pd.DataFrame(rows)
    if long_df.empty:
        return pd.DataFrame()

    heatmap_df = long_df.pivot_table(
        index=["ID", "Product_Name"], 
        columns="Ingredient",
        values="Concentration",
        fill_value=0
    ).reset_index()

    return heatmap_df

def Create_Altair_Heatmap(heatmap_df, drug_of_interest_id):
    if heatmap_df.empty:
        return alt.Chart(pd.DataFrame({'text': ['No data to display']})).mark_text().encode(text='text:N')

    cols_to_norm = heatmap_df.columns.difference(['ID', 'Product_Name'])
    norm_df = heatmap_df.copy()
    
    norm_df[cols_to_norm] = norm_df[cols_to_norm].apply(
        lambda x: x / x.max() if x.max() != 0 else 0
    )

    df_long = norm_df.melt(
        id_vars=["ID", "Product_Name"],
        var_name="Ingredient",
        value_name="Relative_Conc"
    )

    raw_long = heatmap_df.melt(
        id_vars=["ID", "Product_Name"],
        var_name="Ingredient",
        value_name="Raw_Concentration"
    )
    df_long["Concentration"] = raw_long["Raw_Concentration"]

    df_long = df_long[df_long["Relative_Conc"] > 0].copy()
    df_long["Is_Interest"] = df_long["ID"].astype(str) == str(drug_of_interest_id)

    chart = alt.Chart(df_long).mark_rect().encode(
        x=alt.X('Ingredient:N', axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('Product_Name:N', sort=None),
        color=alt.Color(
            'Relative_Conc:Q',
            scale=alt.Scale(scheme='blues', domain=[0, 1]),
            title='Relative Conc.'
        ),
        stroke=alt.condition(
            alt.datum.Is_Interest, 
            alt.value('black'), 
            alt.value(None)
        ),
        strokeWidth=alt.condition(
            alt.datum.Is_Interest, 
            alt.value(2.5), 
            alt.value(0)
        ),
        tooltip=[
            'Product_Name',
            'Ingredient',
            alt.Tooltip('Concentration:Q', title='Actual Dose (mg)'),
            alt.Tooltip('Relative_Conc:Q', format='.2f', title='Rel. Strength')
        ]
    ).properties(
        width='container',
        height=400,
        title="Normalized Ingredient Heatmap (Related Drugs)"
    )

    return chart
