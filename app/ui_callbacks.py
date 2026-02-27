from dash import html, no_update, ctx
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
import umap

from app.helpers import (
    Searchbar,
    Fetch_Ingredients,
    Fetch_Dose_Form,
    Fetch_Generic_Name,
    Exact_drugs,
    Union_Drugs,
    Fetch_Matches,
    Fetch_Heatmap,
    Create_Altair_Heatmap,
    Create_UMAP_Cluster,
    Create_Ingredient_Frequency_Bar,
)

def _to_str_id_list(lst):
    return [str(x) for x in (lst or []) if pd.notna(x)]

def register_callbacks(app):

    # ------------------------------------------------------------
    # 1) SEARCH DROPDOWN OPTIONS
    # ------------------------------------------------------------
    @app.callback(
        Output("drug-search-dropdown", "options"),
        Input("drug-search-dropdown", "search_value")
    )
    def update_options(search_value):
        if not search_value or len(search_value) < 3:
            return []

        df = Searchbar(search_value)
        if df is None or df.empty:
            return []

        if "Product_Name" not in df.columns or "RXCUI" not in df.columns:
            return []

        return [
            {"label": row["Product_Name"], "value": f"{row['Product_Name']}|{row['RXCUI']}"}
            for _, row in df.iterrows()
        ]


    # ------------------------------------------------------------
    # 2) SAVE SELECTED DRUG
    # ------------------------------------------------------------
    @app.callback(
        Output("selected-drug-store", "data"),
        Input("drug-search-dropdown", "value"),
        prevent_initial_call=True
    )
    def save_selection(selected_value):
        if not selected_value:
            return None
        name, rxcui = selected_value.split("|")
        return {"id": str(rxcui), "name": name}


    # ------------------------------------------------------------
    # 3) DRUG INFO CARD + INGREDIENT STORES
    # ------------------------------------------------------------
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

        rxcui = str(stored_data["id"])

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
                html.Li(f"{row['Ingredient']} ({row.get('Concentration', '')} MG)")
                for _, row in (ing_df.iterrows() if ing_df is not None else [])
            ]),
            html.P([html.Strong("RXCUI:"), html.Code(rxcui)])
        ])

        return layout, ing_ids, ing_names


    # ------------------------------------------------------------
    # 4) COMPUTE exact + related ONCE AND STORE
    # ------------------------------------------------------------
    @app.callback(
        Output("matches-store", "data"),
        [
            Input("ingredient-ids-store", "data"),
            State("selected-drug-store", "data"),
        ],
        prevent_initial_call=True
    )
    def compute_matches(ing_ids, selected_drug):
        if not ing_ids or not selected_drug:
            return None

        ID = str(selected_drug["id"])
        ing_lst = _to_str_id_list(ing_ids)

        if len(ing_lst) == 0:
            return None

        exact_df = Exact_drugs(ing_lst, ID)
        union_df = Union_Drugs(ing_lst, ID)
        exact_df2, related_df = Fetch_Matches(exact_df, union_df, ID)

        return {
            "exact": exact_df2.to_dict("records") if exact_df2 is not None else [],
            "related": related_df.to_dict("records") if related_df is not None else [],
        }


    # ------------------------------------------------------------
    # 5) SHOW TOP5 EXACT + CONTROL THE OPEN MODAL BUTTON
    #    open-modal MUST exist in layout initially (hidden)
    # ------------------------------------------------------------
    @app.callback(
        [
            Output("exact-matches-content", "children"),
            Output("open-modal", "children"),
            Output("open-modal", "style"),
        ],
        Input("matches-store", "data"),
        prevent_initial_call=True
    )
    def display_exact_matches(matches_data):
        hide_style = {"display": "none"}

        if not matches_data or not matches_data.get("exact"):
            return html.P("No branded matches found.", className="text-muted"), "View all", hide_style

        df_matches = pd.DataFrame(matches_data["exact"])
        if df_matches.empty:
            return html.P("No branded matches found.", className="text-muted"), "View all", hide_style

        top_5 = df_matches.head(5)
        list_items = dbc.ListGroup(
            [dbc.ListGroupItem(row["Product_Name"], className="py-2") for _, row in top_5.iterrows()],
            flush=True
        )

        if len(df_matches) > 5:
            return (
                html.Div([list_items]),
                f"View all {len(df_matches)} equivalents...",
                {"display": "inline"}
            )

        return html.Div([list_items]), "View all", hide_style


    # ------------------------------------------------------------
    # 6) MODAL TOGGLE
    # ------------------------------------------------------------
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
            State("matches-store", "data"),
        ],
        prevent_initial_call=True
    )
    def toggle_modal(n_open, n_close, is_open, matches_data):
        trigger_id = ctx.triggered_id

        if trigger_id == "open-modal" and n_open:
            if not matches_data or not matches_data.get("exact"):
                return True, html.P("No results.", className="text-muted")

            df_full = pd.DataFrame(matches_data["exact"])
            full_list = dbc.ListGroup(
                [dbc.ListGroupItem(row["Product_Name"]) for _, row in df_full.iterrows()],
                flush=True
            )
            return True, full_list

        if trigger_id == "close-modal" and n_close:
            return False, no_update

        return is_open, no_update


    # ------------------------------------------------------------
    # 7) BUILD heatmap_df ONCE (store it)
    # ------------------------------------------------------------
    @app.callback(
        Output("heatmap-df-store", "data"),
        [
            Input("matches-store", "data"),
            State("selected-drug-store", "data"),
        ],
        prevent_initial_call=True
    )
    def build_heatmap_df(matches_data, selected_drug):
        if not matches_data or not selected_drug:
            return None

        related_records = matches_data.get("related", [])
        if not related_records:
            return None

        related_df = pd.DataFrame(related_records)
        if "ID" not in related_df.columns or "Product_Name" not in related_df.columns:
            return None

        heatmap_df = Fetch_Heatmap(
            related_df[["ID", "Product_Name"]],
            str(selected_drug["id"]),
            selected_drug["name"],
        )

        if heatmap_df is None or heatmap_df.empty:
            return None

        return heatmap_df.to_dict("records")


    # ------------------------------------------------------------
    # 8) UMAP (FIRST) — from stored heatmap_df
    # ------------------------------------------------------------
    @app.callback(
        Output("umap-iframe", "srcDoc"),
        [
            Input("heatmap-df-store", "data"),
            State("selected-drug-store", "data"),
        ],
        prevent_initial_call=True
    )
    def update_umap(heatmap_records, selected_drug):
        if not heatmap_records or not selected_drug:
            return "<h4>No data available</h4>"

        heatmap_df = pd.DataFrame(heatmap_records)

        chart = Create_UMAP_Cluster(
            heatmap_df,
            drug_of_interest_name=selected_drug["name"],
            doseform_weight=2.0,
            jitter_strength=0.15
        )
        return chart.to_html()


    # ------------------------------------------------------------
    # 9) HEATMAP (SECOND) — from stored heatmap_df
    # ------------------------------------------------------------
    @app.callback(
        Output("heatmap-iframe", "srcDoc"),
        Input("heatmap-df-store", "data"),
        State("selected-drug-store", "data"),
        prevent_initial_call=True
    )
    def update_heatmap(heatmap_records, selected_drug):
        if not heatmap_records or not selected_drug:
            return "<h4>No data available for heatmap</h4>"

        heatmap_df = pd.DataFrame(heatmap_records)
        chart = Create_Altair_Heatmap(heatmap_df, str(selected_drug["id"]))
        return chart.to_html()


    # ------------------------------------------------------------
    # 10) BAR (THIRD) — from stored heatmap_df
    # ------------------------------------------------------------
    @app.callback(
        Output("bar-iframe", "srcDoc"),
        Input("heatmap-df-store", "data"),
        prevent_initial_call=True
    )
    def update_bar(heatmap_records):
        if not heatmap_records:
            return "<h4>No data available</h4>"

        heatmap_df = pd.DataFrame(heatmap_records)
        chart = Create_Ingredient_Frequency_Bar(heatmap_df)
        return chart.to_html()