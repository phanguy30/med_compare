import dash
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
import re
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from dash.dependencies import Input, Output, State

load_dotenv()

# --- Database Setup ---
engine = create_engine(f"mysql+pymysql://root:@localhost:3306/rxnorm?charset=utf8mb4")

# --- Helper Functions ---

def extract_name(df):
    """Extracts bracketed text, titles it, and removes duplicates."""
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
    """
    Fetches ingredients and parses the strength (MG) from the name string.
    """
    query = text("""
        SELECT r.RXCUI2 as Ingredient_ID, c.STR as Full_Ingredient
        FROM RXNCONSO c
        JOIN RXNREL r ON c.RXCUI = r.RXCUI2
        WHERE r.RXCUI1 = :id AND c.TTY = "SCDC"
        GROUP BY Ingredient_ID, Full_Ingredient;
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"id": ID})
    
    # Parse the 'Strength' out of the RxNorm SCDC string (e.g., "Amoxicillin 500 MG")
    parsed_data = []
    for _, row in df.iterrows():
        match = re.search(r"(.+?)\s+(\d+(?:\.\d+)?)\s+MG", row["Full_Ingredient"], re.IGNORECASE)
        if match:
            parsed_data.append({
                "Ingredient_ID": row["Ingredient_ID"],
                "Ingredient": match.group(1).strip(),
                "Concentration": match.group(2)
            })
        else:
            parsed_data.append({
                "Ingredient_ID": row["Ingredient_ID"],
                "Ingredient": row["Full_Ingredient"],
                "Concentration": "N/A"
            })
    
    return pd.DataFrame(parsed_data)

def Fetch_Dose_Form(ID):
    query = text("SELECT c.STR FROM RXNCONSO c JOIN RXNREL r ON c.RXCUI = r.RXCUI2 WHERE r.RXCUI1 = :id AND c.TTY = 'DF'")
    with engine.connect() as conn:
        res = pd.read_sql(query, conn, params={'id': ID})
    return res["STR"].iloc[0] if not res.empty else "Not specified"

def fetch_generic_name(ID):
    query = text("SELECT c.STR FROM RXNCONSO c JOIN RXNREL r ON c.RXCUI = r.RXCUI2 WHERE r.RXCUI1 = :id AND c.TTY = 'SCD'")
    with engine.connect() as conn:
        res = pd.read_sql(query, conn, params={'id': ID})
    return res["STR"].iloc[0] if not res.empty else "N/A"

def Fetch_Exact_Drugs(Ing_lst, ing_names current_id):
    if not Ing_lst:
        return pd.DataFrame()

    ing_tuple = tuple(Ing_lst) if len(Ing_lst) > 1 else f"('{Ing_lst[0]}')"

    query = f"""
    SELECT 
        r2.RXCUI as RXCUI, 
        r2.STR as STR
    FROM RXNREL r1
    JOIN RXNCONSO r2 ON r1.RXCUI2 = r2.RXCUI
    WHERE r1.RXCUI1 IN {ing_tuple} 
      AND r2.TTY = 'DP'
      AND r2.RXCUI != :current_id
    GROUP BY r2.RXCUI, r2.STR
    HAVING COUNT(DISTINCT r1.RXCUI1) = :ing_count
    """
    
    with engine.connect() as conn:
        res = pd.read_sql(text(query), conn, params={
            'current_id': current_id, 
            'ing_count': len(Ing_lst)
        })
    
    if not res.empty:
        # 1. First, filter out any row that doesn't have brackets []
        # The regex '\[.*\]' looks for an opening bracket, any text, then a closing bracket
        res = res[res['STR'].str.contains(r'\[.*\]', na=False)]
        
        # 2. Then clean and capitalize using your existing function
        res = extract_name(res)
        res.reset_index(drop=True, inplace=True)
        
    return res


# --- Initialize App ---
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CERULEAN])

app.layout = dbc.Container([
    dcc.Store(id='selected-drug-store'),
    dcc.Store(id='ingredient-ids-store'),

    html.H2("Drug Identity Dashboard", className="text-center mt-4"),
    html.Hr(),
    
    dbc.Row([
        dbc.Col([
            html.Label("Search for a Drug:"),
            dcc.Dropdown(id="drug-search-dropdown", placeholder="Type to search...", searchable=True, clearable=True)
        ], width=6)
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4("Drug Information")),
                dbc.CardBody(id="drug-info-content", children="Select a drug to view details.")
            ])
        ], width=6),
        
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4("Branded Equivalents")),
                dbc.CardBody(id="exact-matches-content", children="No data loaded.")
            ])
        ], width=6)
    ])
], fluid=True)

# --- Callbacks ---

@app.callback(
    Output("drug-search-dropdown", "options"),
    Input("drug-search-dropdown", "search_value")
)
def update_options(search_value):
    if not search_value or len(search_value) < 3: return []
    df = Searchbar(search_value)
    return [{'label': row['Product_Name'], 'value': f"{row['Product_Name']}|{row['RXCUI']}"} for _, row in df.iterrows()]

@app.callback(
    Output("selected-drug-store", "data"),
    Input("drug-search-dropdown", "value"),
    prevent_initial_call=True
)
def save_selection(selected_value):
    if not selected_value: return None
    name, rxcui = selected_value.split('|')
    return {'id': rxcui, 'name': name}

@app.callback(
    [Output("drug-info-content", "children"),
     Output("ingredient-ids-store", "data")],
    Input("selected-drug-store", "data"),
    prevent_initial_call=True
)
def update_drug_info_card(stored_data):
    if not stored_data: return "Select a drug.", None
    rxcui = stored_data['id']
    
    ing_df = Fetch_Ingredients(rxcui)
    ing_ids = ing_df["Ingredient_ID"].tolist() if not ing_df.empty else []
    
    dose_form = Fetch_Dose_Form(rxcui)
    generic_full_name = fetch_generic_name(rxcui)

    layout = html.Div([
        html.H4(stored_data['name'], className="text-primary mb-3"),
        html.P([html.Strong("Generic Formula: "), html.Br(), html.Small(generic_full_name)]),
        html.P([html.Strong("Dose Form: "), dose_form]),
        html.P(html.Strong("Ingredients:")),
        html.Ul([html.Li(f"{row['Ingredient']} ({row['Concentration']} MG)") for _, row in ing_df.iterrows()]),
        html.P([html.Strong("RXCUI: "), html.Code(rxcui)])
    ])
    return layout, ing_ids

@app.callback(
    Output("exact-matches-content", "children"),
    Input("ingredient-ids-store", "data"),
    State("selected-drug-store", "data"),
    prevent_initial_call=True
)
def display_exact_matches(ing_ids, selected_drug):
    if not ing_ids: return "No ingredients found."
    
    df_matches = Fetch_Exact_Drugs(ing_ids, selected_drug['id'])
    
    if df_matches.empty: 
        return html.P("No branded matches found.", className="text-muted")

    return html.Div([
        html.H5(f"Found {len(df_matches)} matches:", className="text-success"),
        html.Ul([html.Li(row['Product_Name']) for _, row in df_matches.iterrows()])
    ])

if __name__ == "__main__":
    app.run(debug=True)