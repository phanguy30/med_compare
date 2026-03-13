from dash import Dash
import dash_bootstrap_components as dbc
import os
import numpy as np
import umap

from app.layout import create_layout
from app.ui_callbacks import register_callbacks
from app.helpers import ensure_sqlite_indexes



app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.CERULEAN],
    suppress_callback_exceptions=True
)

server = app.server

ensure_sqlite_indexes()

app.layout = create_layout()
register_callbacks(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8051))
    app.run(host="0.0.0.0", port=port, debug=False)