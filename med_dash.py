import dash
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
import re
import altair as alt
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from dash.dependencies import Input, Output, State

load_dotenv()

# --- Database Setup ---
engine = create_engine(f"mysql+pymysql://root:@localhost:3306/rxnorm?charset=utf8mb4")

# --- Helper Functions ---
def Fetch_Related_Drugs(Ing_lst, current_id):
    if not Ing_lst:
        return pd.DataFrame(columns=["RXCUI", "STR", "Product_Name"])

    ing_tuple = tuple(Ing_lst) if len(Ing_lst) > 1 else f"('{Ing_lst[0]}')"

    # Handle single vs multi ingredient properly
    if len(Ing_lst) == 1:
        having_clause = "COUNT(DISTINCT r1.RXCUI1) >= 1"
    else:
        having_clause = """
            COUNT(DISTINCT r1.RXCUI1) > 0
            AND COUNT(DISTINCT r1.RXCUI1) < :ing_count
        """

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
    HAVING {having_clause}
    """
    
    with engine.connect() as conn:
        res = pd.read_sql(text(query), conn, params={
            'current_id': current_id, 
            'ing_count': len(Ing_lst)
        })
    
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

def Fetch_Exact_Drugs(Ing_lst, ing_names, current_id):
    """
    Finds drugs that contain EXACTLY the same set of ingredients as the input.
    No more, no less.
    """
    if not Ing_lst:
        return pd.DataFrame(columns=["RXCUI", "Product_Name"])

    ing_tuple = tuple(Ing_lst) if len(Ing_lst) > 1 else f"('{Ing_lst[0]}')"

    query = f"""
    SELECT r2.RXCUI, r2.STR
    FROM RXNCONSO r2
    WHERE r2.TTY = 'DP' 
      AND r2.RXCUI != :current_id
      -- 1. Ensure it matches all the ingredients we provided
      AND r2.RXCUI IN (
          SELECT RXCUI2 
          FROM RXNREL 
          WHERE RXCUI1 IN {ing_tuple}
          GROUP BY RXCUI2
          HAVING COUNT(DISTINCT RXCUI1) = :ing_count
      )
      -- 2. Ensure its TOTAL ingredient count is exactly the same as our list
      -- This filters out drugs that have 'Your 2 + 1 extra'
      AND (
          SELECT COUNT(DISTINCT RXCUI1) 
          FROM RXNREL 
          WHERE RXCUI2 = r2.RXCUI 
          AND RELA = 'consists_of'
      ) = :ing_count
    """
    
    with engine.connect() as conn:
        res = pd.read_sql(text(query), conn, params={
            'current_id': current_id, 
            'ing_count': len(Ing_lst)
        })
    
    if not res.empty:
        # Standard cleaning logic
        res = res[res['STR'].str.contains(r'\[.*\]', na=False)].copy()
        res = extract_name(res)
        
        # Filter out rows where the product name contains an ingredient name
        if ing_names:
            for name in ing_names:
                res = res[~res['Product_Name'].str.contains(re.escape(name), case=False, na=False)]
        
        res.reset_index(drop=True, inplace=True)
        return res[["RXCUI", "Product_Name"]]
        
    return pd.DataFrame(columns=["RXCUI", "Product_Name"])

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


# --- Initialize App ---
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CERULEAN])

app.layout = dbc.Container([
    dcc.Store(id='selected-drug-store'),
    dcc.Store(id='ingredient-ids-store'),
    dcc.Store(id='ingredient-names-store'),

    html.H2("Drug Identity Dashboard", className="text-center mt-4"),
    html.Hr(),
    
    dbc.Row([
        dbc.Col([
            html.Label("Search for a Drug:"),
            dcc.Dropdown(id="drug-search-dropdown", placeholder="Type to search...", searchable=True, clearable=True)
        ], width=6)
    ], className="mb-4"),

   dbc.Row([
        # Left Column: Drug Info
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4("Drug Information")),
                dbc.CardBody(id="drug-info-content", children="Select a drug to view details.")
            ])
        ], width=6),
        
        # Right Column: Branded Equivalents + The Hidden Modal
        dbc.Col([
            # The Modal (Hidden by default, does not affect layout flow)
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle("All Branded Equivalents")),
                dbc.ModalBody(id="full-branded-list-modal-body"),
                dbc.ModalFooter(
                    dbc.Button("Close", id="close-modal", className="ms-auto", n_clicks=0)
                ),
            ], id="branded-modal", is_open=False, scrollable=True),

            # The Visible Card
            dbc.Card([
                dbc.CardHeader(html.H4("Branded Equivalents")),
                dbc.CardBody(id="exact-matches-content", children="No data loaded.")
            ])
        ], width=6)
    ]),

    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4("Ingredient Concentration Heatmap (Related Drugs)")),
                dbc.CardBody([
                    html.Iframe(
                        id="heatmap-iframe", 
                        style={"border": "none", "width": "100%", "height": "550px"}
                    )
                ])
            ], className="mt-4 mb-5")
        ], width=12)
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
     Output("ingredient-ids-store", "data"),
     Output("ingredient-names-store", "data")],
    Input("selected-drug-store", "data"),
    prevent_initial_call=True
)
def update_drug_info_card(stored_data):
    if not stored_data: return "Select a drug.", None, None
    rxcui = stored_data['id']
    
    ing_df = Fetch_Ingredients(rxcui)
    ing_ids = ing_df["Ingredient_ID"].tolist() if not ing_df.empty else []
    ing_names = ing_df["Ingredient"].tolist() if not ing_df.empty else []
    
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
    return layout, ing_ids, ing_names

# MODIFIED: Shows only top 5 and a "View All" button if needed
@app.callback(
    Output("exact-matches-content", "children"),
    [Input("ingredient-ids-store", "data"),
     Input("ingredient-names-store", "data")],
    State("selected-drug-store", "data"),
    prevent_initial_call=True
)
def display_exact_matches(ing_ids, ing_names, selected_drug):
    if not ing_ids: return "No ingredients found."
    
    df_matches = Fetch_Exact_Drugs(ing_ids, ing_names, selected_drug['id'])
    
    if df_matches.empty: 
        return html.P("No branded matches found.", className="text-muted")

    # Slice for the default view
    top_5 = df_matches.head(5)
    
    list_items = dbc.ListGroup(
        [dbc.ListGroupItem(row['Product_Name'], className="py-2") for _, row in top_5.iterrows()],
        flush=True
    )

    content = [list_items]

    # Add toggle button only if list exceeds 5
    if len(df_matches) > 5:
        content.append(
            dbc.Button(
                f"View all {len(df_matches)} equivalents...", 
                id="open-modal", 
                color="link", 
                size="sm", 
                className="mt-2 p-0"
            )
        )
    
    return html.Div(content)

# NEW: Handles the Modal Overlay (Expansion)
@app.callback(
    [Output("branded-modal", "is_open"), 
     Output("full-branded-list-modal-body", "children")],
    [Input("open-modal", "n_clicks"), 
     Input("close-modal", "n_clicks")],
    [State("branded-modal", "is_open"),
     State("ingredient-ids-store", "data"),
     State("ingredient-names-store", "data"),
     State("selected-drug-store", "data")],
    prevent_initial_call=True
)
def toggle_modal(n_open, n_close, is_open, ing_ids, ing_names, selected_drug):
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_open, dash.no_update
    
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger_id == "open-modal" and n_open:
        # Fetch the full list for the modal body
        df_full = Fetch_Exact_Drugs(ing_ids, ing_names, selected_drug['id'])
        full_list = dbc.ListGroup(
            [dbc.ListGroupItem(row['Product_Name']) for _, row in df_full.iterrows()],
            flush=True
        )
        return True, full_list
    
    return False, dash.no_update

@app.callback(
    Output("heatmap-iframe", "srcDoc"),
    [Input("ingredient-ids-store", "data")],
    State("selected-drug-store", "data"),
    prevent_initial_call=True
)
def update_heatmap(ing_ids, selected_drug):
    if not ing_ids or not selected_drug: 
        return ""
    
    related_df = Fetch_Related_Drugs(ing_ids, selected_drug['id'])
    
    if not related_df.empty:
        related_df = related_df.rename(columns={"RXCUI": "ID"})
    else:
        related_df = pd.DataFrame(columns=["ID", "Product_Name"])

    heatmap_df = Fetch_Heatmap(related_df, selected_drug['id'], selected_drug['name'])
    
    if heatmap_df.empty:
        return "<h4>No data available for heatmap</h4>"

    chart = Create_Altair_Heatmap(heatmap_df, selected_drug['id'])
    return chart.to_html()

if __name__ == "__main__":
    app.run(debug=True)