from dash import html, dcc
import dash_bootstrap_components as dbc

def create_layout():
    return dbc.Container([

        # ----------------------------
        # STORES
        # ----------------------------
        dcc.Store(id="selected-drug-store"),
        dcc.Store(id="ingredient-ids-store"),
        dcc.Store(id="ingredient-names-store"),
        dcc.Store(id="matches-store"),
        dcc.Store(id="heatmap-df-store"),

        html.H2("Drug Explorer", className="my-4"),

        # ----------------------------
        # SEARCH
        # ----------------------------
        dcc.Dropdown(
            id="drug-search-dropdown",
            placeholder="Search for a drug..."
        ),

        html.Hr(),

        # =========================================================
        # ROW 1: Drug Info (left) + Exact Matches (right)
        # =========================================================
        dbc.Row([
            dbc.Col([
                html.H4("Drug Information", className="mb-3"),
                dbc.Card(
                    dbc.CardBody(
                        html.Div(id="drug-info-content")
                    ),
                    className="shadow-sm"
                ),
            ], md=6),

            dbc.Col([
                html.H4("Exact Matches"),
                html.Div(id="exact-matches-content"),

                dbc.Button(
                    "View all equivalents...",
                    id="open-modal",
                    color="link",
                    size="sm",
                    className="mt-2 p-0",
                    style={"display": "none"}
                ),
            ], md=6),

        ], className="mb-4"),

        # =========================================================
        # VIEW TOGGLE FOR ROW 2 / ROW 3
        # =========================================================
        dbc.Row([
            dbc.Col([
                html.H4("Similar Product Discovery", className="mb-3"),
                dbc.RadioItems(
                    id="main-view-toggle",
                    className="btn-group",
                    inputClassName="btn-check",
                    labelClassName="btn btn-outline-primary",
                    labelCheckedClassName="active",
                    options=[
                        {
                            "label": "Similarity + Heatmap",
                            "value": "linked_plot"
                        },
                        {
                            "label": "Alternative Combinations",
                            "value": "bar_charts"
                        },
                    ],
                    value="linked_plot",
                ),
            ], md=12),
        ], className="mb-3"),

        # =========================================================
        # ROW 2 CONTENT: LINKED UMAP + HEATMAP
        # =========================================================
        html.Div(
            id="linked-plot-container",
            children=[
                dbc.Row([
                    dbc.Col([
                        html.Iframe(
                            id="linked-plot-iframe",
                            style={
                                "width": "100%",
                                "height": "900px",
                                "border": "none"
                            }
                        ),
                    ], md=12),
                ], className="mb-4"),
            ],
            style={"display": "block"},
        ),

        # =========================================================
        # ROW 3 CONTENT: BAR CHARTS
        # =========================================================
        html.Div(
            id="bar-charts-container",
            children=[
                dbc.Row([
                    dbc.Col([
                        dbc.Tabs([
                            dbc.Tab(
                                html.Iframe(
                                    id="ingredient-bar-iframe",
                                    style={
                                        "width": "100%",
                                        "height": "500px",
                                        "border": "none"
                                    },
                                ),
                                label="Ingredient Frequency",
                            ),
                            dbc.Tab(
                                html.Iframe(
                                    id="combination-bar-iframe",
                                    style={
                                        "width": "100%",
                                        "height": "500px",
                                        "border": "none"
                                    },
                                ),
                                label="Combination Frequency",
                            ),
                        ], className="mb-3"),
                    ], md=12),
                ], className="mb-4"),
            ],
            style={"display": "none"},
        ),

        # ----------------------------
        # MODAL
        # ----------------------------
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("All Exact Matches")),
                dbc.ModalBody(id="full-branded-list-modal-body"),
                dbc.ModalFooter(
                    dbc.Button("Close", id="close-modal", className="ms-auto")
                ),
            ],
            id="branded-modal",
            size="lg",
            is_open=False,
        ),

    ], fluid=True)