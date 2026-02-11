# Interactive Drug Identity & Comparison Dashboard  
## Project Proposal

---

## 1. Project Overview

This project builds an interactive dashboard that helps users:

- Understand how brand, generic, and ingredient names relate  
- Explore similar drug formulations  
- Compare drug compositions visually  
- Reduce confusion caused by redundant product naming  

The system is powered by **RxNorm**, a standardized drug terminology database, and optionally enriched with pharmacologic class metadata.

The dashboard focuses on **identity clarification and formulation comparison**, not medical advice.

---

## 2. Core Problem

Consumers frequently encounter:

- Multiple brand names for the same drug  
- Combination products that appear unique but share similar ingredients  
- Difficulty understanding whether two products are truly different  
- Confusion around generic vs name-brand equivalence  
- Uncertainty about whether higher-priced options offer meaningful differences  

As a result, purchasing decisions are often influenced by branding rather than formulation clarity.

This dashboard addresses the question:

> “Are these drugs actually different, or simply marketed differently?”

By focusing on active ingredient composition and standardized drug identity (via RxNorm), the system visually highlights formulation equivalence and clarifies when products share the same underlying ingredients.

## 3. Workflow Design

### Step 1 — Search

User enters:
- Brand name  
- Generic name  
- Active ingredient  

The system:
- Normalizes the input to an RxNorm RxCUI  
- Identifies canonical drug identity  

---

### 🧾 Step 2 — Three Primary Panels

After search, the interface displays three coordinated panels.

---

## Panel A: Drug Information Panel

**Purpose:** Understand one drug at a glance.

Includes:
- Drug name (brand / generic)
- Active ingredient(s)
- Functional category (via RxClass)
- Formulation complexity (single vs combination)
- Similarity indicator (relative to searched drug)

### Optional Interaction: View Naming Hierarchy

When clicked:

- Opens a hierarchical brand mapping chart
- Shows Ingredient → Generic → Brand structure
- Combination drugs shown as multi-parent nodes

This panel explains identity confusion.

---

## Panel B: Similarity Cluster View

**Purpose:** Explore related formulations.

Visualization:
- 2D similarity map (UMAP / PCA) or ranked similarity list
- Anchor drug highlighted
- Nearby drugs selectable

User can:
- Click nearby drugs
- Select “Top 10 similar”

This panel supports discovery.

---

## Panel C: Heatmap Comparison (Triggered by Selection)

**Purpose:** Compare selected drugs structurally.

When user selects drugs from cluster:

- Ingredient heatmap appears
  - Rows: selected drugs
  - Columns: ingredients
  - Cell color: presence or dosage

This supports analytical comparison.
### Optional Decision Support Visualization

#### Formulation Equivalence Bar Chart

Displays:
- Distinct formulation groups
- Number of products per formulation
- Anchor formulation highlighted

This answers:

> “How many truly distinct options exist?”

---

## 6. Data Sources

- **RxNorm** (local MySQL database)
  - Drug identity
  - Ingredient relationships
  - Brand mappings

- **RxClass**
  - Provides pharmacologic class mappings linked to RxNorm RxCUIs
  - Used to display high-level functional categories for active ingredients (e.g., Analgesic, NSAID, Antihistamine)
  - Informational only — does not drive similarity clustering or equivalence logic

Optional:
- CMS or curated price bands for contextual pricing

---

## 7. Technical Architecture

Backend:
- MySQL (RxNorm full dataset)
- SQL views for drug–ingredient mapping
- Python for similarity computation (Jaccard or cosine)

Frontend:
- Interactive dashboard (Dash, Streamlit, or React)
- Coordinated multi-panel visualization

---

## 8. Key Differentiators

- Separates identity mapping from similarity clustering  
- Highlights formulation redundancy  
- Uses authoritative terminology (RxNorm)  
- Avoids medical advice while supporting informed comparison  

---

## 9. Expected Impact

Users gain:
- Clarity about brand vs generic equivalence  
- Visual understanding of combination drugs  
- Reduced confusion in pharmacy decision-making  

---

## 10. One-Sentence Summary

An interactive dashboard that uses RxNorm to clarify drug identity, visualize formulation similarity, and reduce brand-based confusion through structured comparison tools.
