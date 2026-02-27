from dash import html, no_update, ctx
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd

from app.helpers import (
    Searchbar,
    Fetch_Ingredients,
    Fetch_Dose_Form,
    Fetch_Generic_Name,
    Exact_drugs,
    Union_Drugs,
    Ing_count,
    Fetch_Matches,
    Fetch_Heatmap,
    Create_Altair_Heatmap,
)

def register_callbacks(app):

    # --- Search dropdown options ---
    @app.callback(
        Output("drug-search-dropdown", "options"),
        Input("drug-search-dropdown", "search_value")
    )
    def update_options(search_value):
        if not search_value or len(search_value) < 3:
            return []

        df = Searchbar(search_value)

        # Defensive: ensure expected cols exist
        if df is None or df.empty:
            return []

        # Expecting at least: Product_Name and RXCUI
        return [
            {
                "label": row["Product_Name"],
                "value": f"{row['Product_Name']}|{row['RXCUI']}"
            }
            for _, row in df.iterrows()
            if "Product_Name" in df.columns and "RXCUI" in df.columns
        ]


    # --- Save selected drug ---
    @app.callback(
        Output("selected-drug-store", "data"),
        Input("drug-search-dropdown", "value"),
        prevent_initial_call=True
    )
    def save_selection(selected_value):
        if not selected_value:
            return None

        name, rxcui = selected_value.split("|")
        return {"id": rxcui, "name": name}


    # --- Drug Info Card ---
    @app.callback(
        [
            Output("drug-info-content", "children"),
            Output("ingredient-ids-store", "data"),
            Output("ingredient-names-store", "data"),
        ],
        Input("selected-drug-store", "data"),
        prevent_initial_call=True
    )
    def update_drug_info_card(stored_data):
        if not stored_data:
            return "Select a drug.", None, None

        rxcui = stored_data["id"]

        ing_df = Fetch_Ingredients(rxcui)
        ing_ids = ing_df["Ingredient_ID"].tolist() if ing_df is not None and not ing_df.empty else []
        ing_names = ing_df["Ingredient"].tolist() if ing_df is not None and not ing_df.empty else []

        dose_form = Fetch_Dose_Form(rxcui)
        generic_full_name = Fetch_Generic_Name(rxcui)

        layout = html.Div([
            html.H4(stored_data["name"], className="text-primary mb-3"),
            html.P([html.Strong("Generic Formula:"), html.Br(), html.Small(generic_full_name)]),
            html.P([html.Strong("Dose Form:"), dose_form]),
            html.P(html.Strong("Ingredients:")),
            html.Ul([
                html.Li(f"{row['Ingredient']} ({row['Concentration']} MG)")
                for _, row in (ing_df.iterrows() if ing_df is not None else [])
            ]),
            html.P([html.Strong("RXCUI:"), html.Code(rxcui)])
        ])

        return layout, ing_ids, ing_names


    # --- Exact Matches (Top 5) ---
    @app.callback(
        Output("exact-matches-content", "children"),
        [
            Input("ingredient-ids-store", "data"),
            Input("ingredient-names-store", "data"),
        ],
        State("selected-drug-store", "data"),
        prevent_initial_call=True
    )
    def display_exact_matches(ing_ids, ing_names, selected_drug):
        if not ing_ids or not selected_drug:
            return "No ingredients found."

        # ✅ Replaced Fetch_Exact_Drugs with Exact_Drugs
        df_matches = Exact_Drugs(
            ing_ids, ing_names, selected_drug["id"], selected_drug["name"]
        )

        if df_matches is None or df_matches.empty:
            return html.P("No branded matches found.", className="text-muted")

        top_5 = df_matches.head(5)

        list_items = dbc.ListGroup(
            [
                dbc.ListGroupItem(row["Product_Name"], className="py-2")
                for _, row in top_5.iterrows()
            ],
            flush=True
        )

        content = [list_items]

        if len(df_matches) > 5:
            content.append(
                dbc.Button(
                    f"View all {len(df_matches)} equivalents...",
                    id="open-modal",
                    color="link",
                    size="sm",
                    className="mt-2 p-0",
                )
            )

        return html.Div(content)


    # --- Modal Toggle ---
    @app.callback(
        [
            Output("branded-modal", "is_open"),
            Output("full-branded-list-modal-body", "children"),
        ],
        [
            Input("open-modal", "n_clicks"),
            Input("close-modal", "n_clicks"),
        ],
        [
            State("branded-modal", "is_open"),
            State("ingredient-ids-store", "data"),
            State("ingredient-names-store", "data"),
            State("selected-drug-store", "data"),
        ],
        prevent_initial_call=True
    )
    def toggle_modal(n_open, n_close, is_open, ing_ids, ing_names, selected_drug):
        trigger_id = ctx.triggered_id

        if trigger_id == "open-modal" and n_open and ing_ids and selected_drug:
            # ✅ Replaced Fetch_Exact_Drugs with Exact_Drugs
            df_full = Exact_Drugs(ing_ids, ing_names, selected_drug["id"], selected_drug["name"])

            if df_full is None or df_full.empty:
                return True, html.P("No results.", className="text-muted")

            full_list = dbc.ListGroup(
                [dbc.ListGroupItem(row["Product_Name"]) for _, row in df_full.iterrows()],
                flush=True
            )
            return True, full_list

        if trigger_id == "close-modal" and n_close:
            return False, no_update

        return is_open, no_update


    # --- Heatmap ---
    @app.callback(
        Output("heatmap-iframe", "srcDoc"),
        Input("ingredient-ids-store", "data"),
        State("selected-drug-store", "data"),
        State("ingredient-names-store", "data"),
        prevent_initial_call=True
    )
    def update_heatmap(ing_ids, selected_drug, ing_names):
        if not ing_ids or not selected_drug:
            return ""

        # ✅ Replaced Fetch_Related_Drugs with Union_Drugs / Fetch_Matches (choose one)
        # --- Recommended: use Union_Drugs as "related drugs" provider ---
        related_df = Union_Drugs(ing_ids, ing_names, selected_drug["id"], selected_drug["name"])

        # Optional: if Ing_count is meant to rank/enrich overlap info
        # related_df = Ing_count(related_df, ing_names)

        # If instead Fetch_Matches is what you want for related drugs, use this:
        # related_df = Fetch_Matches(ing_ids, ing_names, selected_drug["id"], selected_drug["name"])

        if related_df is None or related_df.empty:
            related_df = pd.DataFrame(columns=["ID", "Product_Name"])
        else:
            # Normalize RXCUI -> ID for Fetch_Heatmap
            if "RXCUI" in related_df.columns and "ID" not in related_df.columns:
                related_df = related_df.rename(columns={"RXCUI": "ID"})

            # Ensure columns exist
            if "Product_Name" not in related_df.columns:
                # If your helper uses a different column name, map it here
                # e.g., related_df = related_df.rename(columns={"STR": "Product_Name"})
                pass

        heatmap_df = Fetch_Heatmap(
            related_df,
            selected_drug["id"],
            selected_drug["name"],
        )

        if heatmap_df is None or heatmap_df.empty:
            return "<h4>No data available for heatmap</h4>"

        chart = Create_Altair_Heatmap(heatmap_df, selected_drug["id"])
        return chart.to_html()