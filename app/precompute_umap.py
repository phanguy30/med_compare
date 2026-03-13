from pathlib import Path
import pandas as pd

from app.helpers import (
    Searchbar_exact_product,
    Fetch_Ingredients,
    Exact_drugs,
    Union_Drugs,
    Fetch_Matches,
    Fetch_Heatmap,
    Create_Linked_UMAP_Heatmap,
)

BASE_DIR = Path(__file__).resolve().parent
PRECOMPUTED_DIR = BASE_DIR / "assets" / "precomputed"
PRECOMPUTED_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_DRUGS = [
    "Tylenol",
    "Excedrin",
]

def _to_str_id_list(lst):
    return [str(x) for x in (lst or []) if pd.notna(x)]

def build_sample(drug_name):
    selected = Searchbar_exact_product(drug_name)
    if not selected:
        print(f"[SKIP] Could not resolve {drug_name}")
        return

    drug_id = str(selected["id"])
    resolved_name = selected["name"]

    ing_df = Fetch_Ingredients(drug_id)
    if ing_df is None or ing_df.empty:
        print(f"[SKIP] No ingredients found for {drug_name}")
        return

    ing_ids = _to_str_id_list(ing_df["Ingredient_ID"].tolist())

    exact_df = Exact_drugs(ing_ids, drug_id)
    union_df = Union_Drugs(ing_ids, drug_id)
    exact_df2, related_df = Fetch_Matches(exact_df, union_df, drug_id)

    if related_df is None or related_df.empty:
        print(f"[SKIP] No related products found for {drug_name}")
        return

    heatmap_df = Fetch_Heatmap(
        related_df[["ID", "Product_Name"]],
        drug_id,
        resolved_name,
    )

    if heatmap_df is None or heatmap_df.empty:
        print(f"[SKIP] No heatmap data for {drug_name}")
        return

    chart = Create_Linked_UMAP_Heatmap(
        heatmap_df=heatmap_df,
        drug_of_interest=drug_id,
        match_by="ID",
        doseform_weight=2.0
    )

    output_file = PRECOMPUTED_DIR / f"{drug_name.strip().lower()}_linked_plot.html"
    output_file.write_text(chart.to_html(), encoding="utf-8")

    print(f"[OK] Saved {output_file}")

if __name__ == "__main__":
    for drug in SAMPLE_DRUGS:
        build_sample(drug)