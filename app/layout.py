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

        # =========================================================
        # HEADER ROW
        # =========================================================
        dbc.Row([
        dbc.Col(
            html.H2("Drug Explorer", className="fw-semibold"),
            md=12
        )
        ], className="align-items-center mb-3"),



 
        # =========================================================
        # SEARCH + QUICK SAMPLE ROW
        # =========================================================
        dbc.Row([

            # Search
            dbc.Col([
                html.H4("Search Any Drug", className="mb-1"),
                dcc.Dropdown(
                    id="drug-search-dropdown",
                    placeholder="Search for a drug...",
                ),
            ], md=10),

            # Quick Samples
            dbc.Col([
                html.H4("Quick Samples", className="mb-1"),

                dbc.RadioItems(
                    id="sample-drug-buttons",
                    className="d-flex gap-2 justify-content-start",
                    inputClassName="btn-check",
                    labelClassName="btn btn-outline-primary btn-sm",
                    labelCheckedClassName="active",
                    options=[
                        {"label": "Tylenol", "value": "Tylenol"},
                        {"label": "Excedrin", "value": "Excedrin"},
                    ],
                    value="Tylenol",
                ),
            ], md=2),

        ], className="align-items-end mb-2"),

        # =========================================================
        # ROW 1: Drug Info (left) + Exact Matches (right)
        # =========================================================
        dbc.Row([
            dbc.Col([
                html.H4("Drug Information", className="mb-2"),
                dbc.Card(
                    dbc.CardBody(
                        html.Div(
                            id="drug-info-content",
                            style={
                                "fontSize": "0.92rem",
                                "lineHeight": "1.35"
                            }
                        ),
                        style={"padding": "0.75rem"}
                    ),
                    className="shadow-sm"
                ),
            ], md=6),

            dbc.Col([
                html.H4("Exact Matches", className="mb-2"),
                html.Div(
                    id="exact-matches-content",
                    style={
                        "fontSize": "0.92rem",
                        "lineHeight": "1.35"
                    }
                ),
                dbc.Button(
                    "View all equivalents...",
                    id="open-modal",
                    color="link",
                    size="sm",
                    className="mt-1 p-0",
                    style={"display": "none"}
                ),
            ], md=6),
        ], className="mb-2"),

        # =========================================================
        # VIEW TOGGLE
        # =========================================================
        # Title row
        dbc.Row([
            dbc.Col([
                html.H4(
                    "Similar Product Discovery",
                    className="mb-1"
                )
            ], md=12),
        ]),

        # Buttons row
        dbc.Row([
            dbc.Col([
                dbc.RadioItems(
                    id="main-view-toggle",
                    className="btn-group d-flex justify-content-center",
                    inputClassName="btn-check",
                    labelClassName="btn btn-outline-primary btn-sm",
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
        ], className="mb-2"),

        # =========================================================
        # LINKED UMAP + HEATMAP
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
                                "height": "68vh",
                                "minHeight": "520px",
                                "maxHeight": "760px",
                                "border": "none"
                            }
                        ),
                    ], md=12),
                ], className="mb-2"),
            ],
            style={"display": "block"},
        ),

        # =========================================================
        # BAR CHARTS
        # =========================================================
        html.Div(
            id="bar-charts-container",
            children=[
                dbc.Row([
                    dbc.Col([
                        html.Iframe(
                            id="ingredient-bar-iframe",
                            style={
                                "width": "100%",
                                "height": "42vh",
                                "minHeight": "320px",
                                "maxHeight": "420px",
                                "border": "none"
                            },
                        ),
                    ], md=6),

                    dbc.Col([
                        html.Iframe(
                            id="combination-bar-iframe",
                            style={
                                "width": "100%",
                                "height": "42vh",
                                "minHeight": "320px",
                                "maxHeight": "420px",
                                "border": "none"
                            },
                        ),
                    ], md=6),
                ], className="mb-2"),
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

    ], fluid=True, className="px-2 py-2")
