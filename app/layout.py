# layout.py

from dash import dcc, html
import dash_bootstrap_components as dbc

def create_layout():
    return dbc.Container([
        dcc.Store(id='selected-drug-store'),
        dcc.Store(id='ingredient-ids-store'),
        dcc.Store(id='ingredient-names-store'),

        html.H2("Drug Identity Dashboard", className="text-center mt-4"),
        html.Hr(),
        
        dbc.Row([
            dbc.Col([
                html.Label("Search for a Drug:"),
                dcc.Dropdown(
                    id="drug-search-dropdown",
                    placeholder="Type to search...",
                    searchable=True,
                    clearable=True
                )
            ], width=6)
        ], className="mb-4"),

        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H4("Drug Information")),
                    dbc.CardBody(
                        id="drug-info-content",
                        children="Select a drug to view details."
                    )
                ])
            ], width=6),

            dbc.Col([
                dbc.Modal([
                    dbc.ModalHeader(dbc.ModalTitle("All Branded Equivalents")),
                    dbc.ModalBody(id="full-branded-list-modal-body"),
                    dbc.ModalFooter(
                        dbc.Button("Close", id="close-modal", className="ms-auto", n_clicks=0)
                    ),
                ], id="branded-modal", is_open=False, scrollable=True),

                dbc.Card([
                    dbc.CardHeader(html.H4("Branded Equivalents")),
                    dbc.CardBody(
                        id="exact-matches-content",
                        children="No data loaded."
                    )
                ])
            ], width=6)
        ]),

        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(
                        html.H4("Ingredient Concentration Heatmap (Related Drugs)")
                    ),
                    dbc.CardBody([
                        html.Iframe(
                            id="heatmap-iframe",
                            style={
                                "border": "none",
                                "width": "100%",
                                "height": "550px"
                            }
                        )
                    ])
                ], className="mt-4 mb-5")
            ])
        ])
    ], fluid=True)