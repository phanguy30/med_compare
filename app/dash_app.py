from dash import Dash
import dash_bootstrap_components as dbc
from app.layout import create_layout
from app.ui_callbacks import register_callbacks
import os
import numpy as np
import umap

def warm_umap():

    X_dummy = np.random.rand(20, 5).astype("float32")
    reducer = umap.UMAP(
        n_neighbors=5,
        min_dist=0.3,
        n_components=2,
        random_state=42,
        low_memory=True
    )
    reducer.fit_transform(X_dummy)

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.CERULEAN],
    suppress_callback_exceptions=True
)

server = app.server

#Warm up UMAP to reduce latency on first real request
warm_umap()

app.layout = create_layout

register_callbacks(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)