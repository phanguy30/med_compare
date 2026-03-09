from dash import Dash
import dash_bootstrap_components as dbc
from app.layout import create_layout
from app.ui_callbacks import register_callbacks
import os

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.CERULEAN],
    suppress_callback_exceptions=True
)

server = app.server

app.layout = create_layout()

register_callbacks(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)