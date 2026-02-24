import dash
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

# --- Database Setup ---
engine = create_engine(f"mysql+pymysql://root:@localhost:3306/rxnorm?charset=utf8mb4")


def Fetch_Exact_Drugs(Ing_lst, ing_names, current_id):
    if not Ing_lst:
        return pd.DataFrame(columns=["RXCUI", "Product_Name", "STR"])

    query = text("""
        SELECT r2.RXCUI, r2.STR
        FROM RXNCONSO r2
        WHERE r2.TTY IN ('SCD','SBD','GPCK','BPCK','DP')
        AND r2.LAT = 'ENG'
        AND r2.RXCUI IN (
            SELECT r.RXCUI2
            FROM RXNREL r
            WHERE r.RXCUI1 IN :ing_list
                AND r.RELA = 'consists_of'
            GROUP BY r.RXCUI2
            HAVING COUNT(DISTINCT r.RXCUI1) = :ing_count
        )
        AND (
            SELECT COUNT(DISTINCT r3.RXCUI1)
            FROM RXNREL r3
            WHERE r3.RXCUI2 = r2.RXCUI
                AND r3.RELA = 'consists_of'
        ) = :ing_count;
    """).bindparams(bindparam("ing_list", expanding=True))

    with engine.connect() as conn:
        res = pd.read_sql(
            query,
            conn,
            params={
                "current_id": current_id,
                "ing_count": len(Ing_lst),
                "ing_list": Ing_lst
            }
        )

    if res.empty:
        return pd.DataFrame(columns=["RXCUI", "Product_Name", "STR"])

    res = res[res['STR'].str.contains(r'\[.*\]', na=False)].copy()
    res = extract_name(res)

    if ing_names:
        for name in ing_names:
            res = res[~res['Product_Name'].str.contains(
                re.escape(name), case=False, na=False
            )]

    res.reset_index(drop=True, inplace=True)
    return res[["RXCUI", "Product_Name", "STR"]]


def Fetch_Related_Drugs(Ing_lst, current_id):
    if not Ing_lst:
        return pd.DataFrame(columns=["RXCUI", "STR", "Product_Name"])

    query = text("""
        SELECT c.RXCUI, c.STR
        FROM RXNCONSO c
        WHERE c.TTY = 'DP'
          AND c.LAT = 'ENG'
          AND c.RXCUI <> :current_id
          AND EXISTS (
              SELECT 1
              FROM RXNREL r
              WHERE r.RELA = 'consists_of'
                AND r.RXCUI2 = c.RXCUI
                AND r.RXCUI1 IN :ing_list
          )
          AND NOT EXISTS (
              SELECT 1
              FROM (
                  SELECT r2.RXCUI2 AS drug_rxcui
                  FROM RXNREL r2
                  WHERE r2.RELA = 'consists_of'
                    AND r2.RXCUI1 IN :ing_list
                  GROUP BY r2.RXCUI2
                  HAVING COUNT(DISTINCT r2.RXCUI1) = :ing_count
                     AND (
                         SELECT COUNT(DISTINCT r3.RXCUI1)
                         FROM RXNREL r3
                         WHERE r3.RELA = 'consists_of'
                           AND r3.RXCUI2 = r2.RXCUI2
                     ) = :ing_count
              ) exact
              WHERE exact.drug_rxcui = c.RXCUI
          )
    """).bindparams(bindparam("ing_list", expanding=True))

    with engine.connect() as conn:
        res = pd.read_sql(
            query,
            conn,
            params={
                "current_id": current_id,
                "ing_list": Ing_lst,
                "ing_count": len(Ing_lst)
            }
        )

    if not res.empty:
        res = res[res['STR'].str.contains(r'\[.*\]', na=False)].copy()
        res["Product_Name"] = res["STR"].str.extract(r'\[(.*?)\]')
        res["Product_Name"] = res["Product_Name"].str.title()
        res = res.drop_duplicates(subset=["Product_Name"])
        res = res[res["Product_Name"].str.lower() != "generic"]
        res.drop_duplicates(subset="RXCUI", inplace=True)
        res.reset_index(drop=True, inplace=True)

    return res

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
