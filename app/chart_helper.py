import os
import dash
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
import re
import altair as alt
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from dash.dependencies import Input, Output, State
import numpy as np
import umap
from difflib import get_close_matches

alt.data_transformers.disable_max_rows()


def _message_chart(msg, size=14):
    """Return a simple text chart for empty/error states."""
    return alt.Chart(pd.DataFrame({'msg': [msg]})).mark_text(size=size).encode(
        text='msg:N'
    )


def _ensure_product_name(df):
    """Ensure Product_Name exists as a column."""
    if 'Product_Name' not in df.columns:
        df = df.reset_index()
    return df


def _apply_selection(df, drug_of_interest, match_by):
    """
    Add boolean column 'is_selected' based on ID or Product_Name.
    """
    df = df.copy()

    if match_by == 'ID':
        selected_id = str(drug_of_interest).strip()
        df['is_selected'] = df['ID'].astype(str).str.strip().eq(selected_id)

    elif match_by == 'Product_Name':
        selected_name = str(drug_of_interest).strip().lower()
        df['is_selected'] = (
            df['Product_Name'].astype(str).str.strip().str.lower().eq(selected_name)
        )

    else:
        raise ValueError('match_by must be "ID" or "Product_Name"')

    return df


def _build_umap_features(df, doseform_weight=2.0):
    """
    Build the numeric feature matrix used for UMAP:
    ingredient columns + one-hot encoded dose form.
    """
    ignore_cols = {'Product_Name', 'Ingredients_List', 'ID', 'Dose_Form', 'is_selected'}
    ingredient_cols = [c for c in df.columns if c not in ignore_cols]

    df_form = df[['Dose_Form']].copy()
    df_form['Dose_Form'] = df_form['Dose_Form'].fillna('UNKNOWN').astype(str)

    form_ohe = (
        pd.get_dummies(df_form['Dose_Form'], prefix='DF')
        .astype(np.float32) * np.float32(doseform_weight)
    )

    if ingredient_cols:
        X_ing = (
            df[ingredient_cols]
            .apply(pd.to_numeric, errors='coerce')
            .fillna(0)
            .to_numpy(dtype=np.float32)
        )
    else:
        X_ing = np.zeros((len(df), 0), dtype=np.float32)

    X = np.hstack([X_ing, form_ohe.to_numpy(dtype=np.float32)])
    X = np.ascontiguousarray(X, dtype=np.float32)

    return X, ingredient_cols, form_ohe


def _fit_umap(X):
    """Fit UMAP and return 2D embedding."""
    n_samples, _ = X.shape

    if n_samples < 3:
        raise ValueError(
            f"Not enough products to compute UMAP similarity map "
            f"(need at least 3, got {n_samples})."
        )

    n_neighbors = min(10, n_samples - 1)
    n_neighbors = max(2, n_neighbors)

    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=0.3,
        n_components=2,
        metric='euclidean',
        random_state=42,
        low_memory=True,
        n_jobs=1
    )

    return reducer.fit_transform(X)


def _add_embedding_columns(df, embedding, jitter_strength=0.15, seed=42):
    """Attach UMAP coordinates, jittered coordinates, and ingredient string."""
    plot_df = df.copy()
    plot_df['UMAP1'] = embedding[:, 0]
    plot_df['UMAP2'] = embedding[:, 1]

    plot_df['Ingredients_Str'] = plot_df['Ingredients_List'].apply(
        lambda x: ', '.join(x) if isinstance(x, list) else str(x)
    )

    rng = np.random.default_rng(seed)
    plot_df['UMAP1_jitter'] = plot_df['UMAP1'] + rng.normal(0, jitter_strength, len(plot_df))
    plot_df['UMAP2_jitter'] = plot_df['UMAP2'] + rng.normal(0, jitter_strength, len(plot_df))

    return plot_df


def _make_default_heatmap_subset(plot_df, max_related=10):
    """
    Default heatmap subset = selected row(s) + first max_related non-selected rows.
    """
    selected_df = plot_df.loc[plot_df['is_selected']].copy()

    if max_related is not None:
        other_df = plot_df.loc[~plot_df['is_selected']].copy().head(max_related)
    else:
        other_df = plot_df.loc[~plot_df['is_selected']].copy()

    heatmap_subset = pd.concat([selected_df, other_df], ignore_index=True)
    heatmap_subset = (
        heatmap_subset
        .sort_values('is_selected', ascending=False)
        .reset_index(drop=True)
    )

    highlight_title = heatmap_subset.loc[
        heatmap_subset['is_selected'], 'Product_Name'
    ].iloc[0]

    return heatmap_subset, highlight_title


def _get_value_cols(plot_df):
    """Return ingredient/value columns used in the heatmap."""
    non_ingredient_cols = {
        'Product_Name', 'Ingredients_List', 'ID', 'Dose_Form', 'is_selected',
        'UMAP1', 'UMAP2', 'Ingredients_Str', 'UMAP1_jitter', 'UMAP2_jitter',
        'sort_key'
    }
    return [c for c in plot_df.columns if c not in non_ingredient_cols]


def _prepare_long_heatmap_df(df, value_cols, id_vars):
    """
    Melt into long format and compute relative concentration per ingredient.
    """
    df_long = df.melt(
        id_vars=id_vars,
        value_vars=value_cols,
        var_name='Ingredient',
        value_name='Concentration'
    )

    df_long['Product_Name'] = df_long['Product_Name'].astype(str)
    df_long['Ingredient'] = df_long['Ingredient'].astype(str)
    df_long['Concentration'] = pd.to_numeric(
        df_long['Concentration'], errors='coerce'
    ).fillna(0)

    df_long['Relative_Conc'] = (
        df_long.groupby('Ingredient')['Concentration']
        .transform(lambda x: x / x.max() if x.max() != 0 else 0)
    )

    return df_long


def _prepare_brushed_heatmap_input(plot_df):
    """
    Create brushed heatmap source data such that:
    - the selected drug is always ordered first
    """
    df = plot_df.copy()
    df['sort_key'] = np.where(df['is_selected'], 0, 1)
    return df


def _prepare_default_row_bands(heatmap_subset, ingredients):
    """Prepare row-band dataframe for default heatmap."""
    df_rows = heatmap_subset[['Product_Name', 'ID', 'is_selected']].drop_duplicates().copy()
    df_rows['row_index'] = range(len(df_rows))
    df_rows['is_odd'] = df_rows['row_index'] % 2 == 1
    df_rows['x_start'] = ingredients[0]
    df_rows['x_end'] = ingredients[-1]
    return df_rows


def _prepare_brushed_row_bands(plot_df, ingredients):
    """Prepare row-band dataframe for brushed heatmap."""
    df_rows = plot_df[
        ['Product_Name', 'ID', 'is_selected', 'UMAP1_jitter', 'UMAP2_jitter', 'sort_key']
    ].drop_duplicates().copy()

    df_rows = df_rows.sort_values(
        ['sort_key', 'Product_Name'],
        ascending=[True, True]
    ).reset_index(drop=True)

    df_rows['row_index'] = range(len(df_rows))
    df_rows['is_odd'] = df_rows['row_index'] % 2 == 1
    df_rows['x_start'] = ingredients[0]
    df_rows['x_end'] = ingredients[-1]

    return df_rows


def _build_brush():
    """Create shared Altair interval brush selection."""
    return alt.selection_interval(
        name='brush',
        encodings=['x', 'y'],
        clear='dblclick'
    )


def _build_umap_chart(plot_df, brush):
    """Build the linked UMAP scatter plot."""
    tooltips = [
        alt.Tooltip('Product_Name:N', title='Product'),
        alt.Tooltip('ID:N', title='ID'),
        alt.Tooltip('Dose_Form:N', title='Dose Form'),
        alt.Tooltip('Ingredients_Str:N', title='Ingredients')
    ]

    base_points = alt.Chart(plot_df).mark_circle(
        size=80,
        color='steelblue',
        opacity=0.8
    ).encode(
        x=alt.X('UMAP1_jitter:Q', title='UMAP Dimension 1'),
        y=alt.Y('UMAP2_jitter:Q', title='UMAP Dimension 2'),
        tooltip=tooltips
    )

    initial_highlight = alt.Chart(plot_df).transform_filter(
        alt.datum.is_selected
    ).mark_circle(
        size=220,
        color='orange',
        opacity=0.95
    ).encode(
        x='UMAP1_jitter:Q',
        y='UMAP2_jitter:Q',
        tooltip=tooltips
    )

    brushed_highlight = alt.Chart(plot_df).transform_filter(
        "length(data('brush_store'))"
    ).transform_filter(
        brush
    ).mark_circle(
        size=180,
        color='red',
        opacity=1.0
    ).encode(
        x='UMAP1_jitter:Q',
        y='UMAP2_jitter:Q',
        tooltip=tooltips
    )

    return (
        (base_points + initial_highlight + brushed_highlight)
        .add_params(brush)
        .properties(
            width=580,
            height=450,
            title='Drug Similarity Clustering (UMAP) — drag to select products'
        )
    )


def _build_default_heatmap_layers(
    df_long_default,
    df_rows_default,
    default_ingredients,
    default_product_order,
    no_brush
):
    """Build default heatmap layers shown when no brush is active."""
    base = alt.Chart(df_long_default).transform_filter(
        no_brush
    ).encode(
        x=alt.X(
            'Ingredient:N',
            axis=alt.Axis(
            labelAngle=-40,
            labelFontSize=12,
            titleFontSize=13,
            labelLimit=180
            ),
            sort=default_ingredients,
            scale=alt.Scale(padding=0)
        ),
        y=alt.Y('Product_Name:N', sort=default_product_order)
    )

    row_bands = alt.Chart(df_rows_default).transform_filter(
        no_brush
    ).mark_rect(
    stroke='white',
    strokeWidth=1
    ).encode(
        x=alt.X('x_start:N', sort=default_ingredients, scale=alt.Scale(padding=0), title=None),
        x2='x_end:N',
        y=alt.Y('Product_Name:N', sort=default_product_order),
        color=alt.condition(
            alt.datum.is_odd,
            alt.value('#f3f3f3'),
            alt.value('white')
        )
    )


    highlight_zeros = base.transform_filter(
    alt.datum.is_selected & (alt.datum.Concentration == 0)
    ).mark_rect(
    stroke='white',
    strokeWidth=1
    ).encode(
    color=alt.value('#edf2f7')
    )

    nonzero_layer = base.transform_filter(
    alt.datum.Concentration > 0).mark_rect(
    stroke='white',
    strokeWidth=1).encode(
    color=alt.Color(
        'Relative_Conc:Q',
        scale=alt.Scale(scheme='blues', domain=[0, 1]),
        title='Relative Concentration'
    ),
        tooltip=[
            alt.Tooltip('Product_Name:N', title='Product'),
            alt.Tooltip('ID:N', title='ID'),
            alt.Tooltip('Ingredient:N', title='Ingredient'),
            alt.Tooltip('Concentration:Q', title='Concentration (mg)'),
            alt.Tooltip('Relative_Conc:Q', format='.2f', title='Relative')
        ]
    )

    selected_outline = alt.Chart(df_rows_default).transform_filter(
        no_brush
    ).transform_filter(
        alt.datum.is_selected
    ).mark_rect(
        fillOpacity=0,
        stroke='#2b6cb0',
        strokeWidth=2
    ).encode(
        y=alt.Y('Product_Name:N', sort=default_product_order)
    )
    return row_bands + highlight_zeros + nonzero_layer + selected_outline


def _build_brushed_heatmap_layers(
    df_long_brushed,
    df_rows_brushed,
    brushed_ingredients,
    brush,
    has_brush
):
    """Build brushed heatmap layers shown when UMAP brush is active."""
    y_sort = alt.SortField(field='sort_key', order='ascending')

    # Brushed rows
    base_brushed = alt.Chart(df_long_brushed).transform_filter(
        has_brush
    ).transform_filter(
        brush
    ).encode(
        x=alt.X(
            'Ingredient:N',
            axis=alt.Axis(
            labelAngle=-40,
            labelFontSize=12,
            titleFontSize=13,
            labelLimit=180
            ),
            sort=brushed_ingredients,
            scale=alt.Scale(padding=0)
        ),
        y=alt.Y('Product_Name:N', sort=y_sort)
    )

    # Selected row always included when brush is active
    base_selected = alt.Chart(df_long_brushed).transform_filter(
        has_brush
    ).transform_filter(
        alt.datum.is_selected
    ).encode(
        x=alt.X(
            'Ingredient:N',
            axis=alt.Axis(
            labelAngle=-40,
            labelFontSize=12,
            titleFontSize=13,
            labelLimit=180
            ),
            sort=brushed_ingredients,
            scale=alt.Scale(padding=0)
        ),
        y=alt.Y('Product_Name:N', sort=y_sort)
    )

    # Row bands for brushed rows
    row_bands_brushed = alt.Chart(df_rows_brushed).transform_filter(
        has_brush
    ).transform_filter(
        brush
    ).mark_rect(
    stroke='white',
    strokeWidth=1
    ).encode(
        x=alt.X(
            'x_start:N',
            sort=brushed_ingredients,
            scale=alt.Scale(padding=0),
            title=None
        ),
        x2='x_end:N',
        y=alt.Y('Product_Name:N', sort=y_sort),
        color=alt.condition(
            alt.datum.is_odd,
            alt.value('#f3f3f3'),
            alt.value('white')
        )
    )

    # Blue row band for selected drug
    selected_row_band = alt.Chart(df_rows_brushed).transform_filter(
    has_brush
    ).transform_filter(
        alt.datum.is_selected
    ).mark_rect(
        color='#cfe8ff',
        opacity=0.45
    ).encode(
        y=alt.Y('Product_Name:N', sort=y_sort)
    )


    # Brushed non-selected rows
    zero_layer_brushed = base_brushed.transform_filter(
        alt.datum.Concentration == 0
    ).mark_rect(
    stroke='white',
    strokeWidth=1
    ).encode(
        color=alt.value('#edf2f7')
    )

    nonzero_layer_brushed = base_brushed.transform_filter(
    alt.datum.Concentration > 0
    ).mark_rect(
    stroke='white',
    strokeWidth=1
    ).encode(
    color=alt.Color(
        'Relative_Conc:Q',
        scale=alt.Scale(scheme='blues', domain=[0, 1]),
        title='Relative Concentration'
    ),
        tooltip=[
            alt.Tooltip('Product_Name:N', title='Product'),
            alt.Tooltip('ID:N', title='ID'),
            alt.Tooltip('Ingredient:N', title='Ingredient'),
            alt.Tooltip('Concentration:Q', title='Concentration (mg)'),
            alt.Tooltip('Relative_Conc:Q', format='.2f', title='Relative')
        ]
    )

    brushed_outline = base_brushed.transform_filter(
        ~alt.datum.is_selected
    ).mark_rect(
        fillOpacity=0,
        stroke='white',
        strokeWidth=2.0,
        strokeOpacity=1
    )

    text_brushed = base_brushed.transform_filter(
    alt.datum.Concentration > 0
    ).mark_text(
    fontSize=11,
    fontWeight='bold'
    ).encode(
    text=alt.Text('Concentration:Q', format='.0f'),
    color=alt.value('white')
    )

    # Selected row overlay
    zero_layer_selected = base_selected.transform_filter(
        alt.datum.Concentration == 0
    ).mark_rect(
    stroke='white',
    strokeWidth=1
    ).encode(
        color=alt.value('#f8d7da')
    )

    nonzero_layer_selected = base_selected.transform_filter(
    alt.datum.Concentration > 0
    ).mark_rect(
    stroke='white',
    strokeWidth=1
    ).encode(
    color=alt.Color(
        'Relative_Conc:Q',
        scale=alt.Scale(scheme='blues', domain=[0, 1]),
        title='Relative Concentration'
    ),
        tooltip=[
            alt.Tooltip('Product_Name:N', title='Product'),
            alt.Tooltip('ID:N', title='ID'),
            alt.Tooltip('Ingredient:N', title='Ingredient'),
            alt.Tooltip('Concentration:Q', title='Concentration (mg)'),
            alt.Tooltip('Relative_Conc:Q', format='.2f', title='Relative')
        ]
    )

    selected_outline = alt.Chart(df_rows_brushed).transform_filter(
    has_brush
    ).transform_filter(
        alt.datum.is_selected
    ).mark_rect(
        fillOpacity=0,
        stroke='#2b6cb0',
        strokeWidth=3
    ).encode(
        y=alt.Y('Product_Name:N', sort=y_sort)
    )

    text_selected = base_selected.transform_filter(
    alt.datum.Concentration > 0
    ).mark_text(
    fontSize=11,
    fontWeight='bold'
    ).encode(
    text=alt.Text('Concentration:Q', format='.0f'),
    color=alt.value('white')
    )

    return (
        row_bands_brushed
        + selected_row_band
        + zero_layer_brushed
        + nonzero_layer_brushed
        + brushed_outline
        + text_brushed
        + zero_layer_selected
        + nonzero_layer_selected
        + selected_outline
        + text_selected
    )
