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

        html.H2("Drug Explorer", className="my-2"),

        # ----------------------------
        # QUICK SAMPLE DRUGS
        # ----------------------------
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.H5(
                        "Quick Sample Drugs",
                        className="mb-0 me-3"
                    ),
                    dbc.RadioItems(
                        id="sample-drug-buttons",
                        className="btn-group",
                        inputClassName="btn-check",
                        labelClassName="btn btn-outline-primary btn-sm",
                        labelCheckedClassName="active",
                        options=[
                            {"label": "Tylenol", "value": "Tylenol"},
                            {"label": "Excedrin", "value": "Excedrin"},
                        ],
                        value="Tylenol",
                    ),
                ], className="d-flex align-items-center flex-wrap gap-2")
            ], md=12),
        ], className="mb-2"),

        # ----------------------------
        # SEARCH
        # ----------------------------
        html.H5("Search Any Drug", className="mb-1"),
        dcc.Dropdown(
            id="drug-search-dropdown",
            placeholder="Search for a drug...",
            style={"marginBottom": "8px"}
        ),

        html.Hr(className="my-2"),

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
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.H4(
                        "Similar Product Discovery",
                        className="mb-0 me-3"
                    ),
                    dbc.RadioItems(
                        id="main-view-toggle",
                        className="btn-group",
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
                ], className="d-flex align-items-center flex-wrap gap-2")
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
                        html.H5("Ingredient Frequency", className="mb-1"),
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
                        html.H5("Combination Frequency", className="mb-1"),
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
