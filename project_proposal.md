# Interactive Drug Identity & Comparison Dashboard  
## Project Proposal: MedCompare

---

## 1. Motivation and purpose

Our role: Data scientists collaborating with community pharmacies to improve medication transparency.

Target audience: General consumers who do not have technical knowledge of drug ingredients or pharmaceutical naming conventions.

Many medications contain identical active ingredients and dosages but are sold under different brand names at significantly different prices, leading customers to overspend due to brand familiarity. In addition, combination products and derivative formulations can make labels confusing. For example, regular Tylenol contains only acetaminophen, while variants such as Tylenol Sinus may include acetaminophen combined with additional active ingredients (e.g., decongestants), and Tylenol PM combines acetaminophen with a sedating antihistamine. Other formulations, such as Extra Strength versions, contain higher dosages of the same active ingredient. These variations can make it difficult for consumers to understand what they are actually purchasing, and in some cases, additional ingredients may not be necessary for a patient’s specific needs. To address this confusion, we propose an interactive dashboard powered by RxNorm, a public drug terminology database, that visually clarifies the relationships between brand names, generic drugs, and active ingredients. This tool will allow users to compare formulations and better understand what is in the medication they are purchasing. The dashboard supports informed consumer decision-making and does not provide medical advice.


---


### 2. Description of the Data

This project uses the publicly available RxNorm dataset from the U.S. National Library of Medicine (NLM), which provides standardized identifiers and normalized names for clinical drugs and links them across pharmacy and health record systems. The dataset is openly distributed for research and educational use, making it suitable for public dashboard deployment.

The data are stored locally in a MySQL relational database and primarily use three core tables: RXNCONSO, RXNREL, and RXNSAT, which together describe drug identity, composition, and structured relationships.

RXNCONSO contains standardized drug concept records, including unique identifiers (RXCUI), name strings (brand and generic), and term types (e.g., ingredient, clinical drug, brand name). Each entry represents a specific level of abstraction within the drug hierarchy, allowing us to distinguish between active ingredients, generic formulations, and branded products.

RXNREL encodes structured relationships between concepts in RXNCONSO (e.g., has-ingredient, tradename-of), enabling reconstruction of ingredient hierarchies and brand–generic mappings. These relationships allow us to identify combination drugs and visualize structural similarities between formulations.

RXNSAT contains supplemental attributes such as dosage form and strength, which are selectively used to enrich the product comparison panels with formulation details.

Below are some EDA charts to explain the data: 

<img width="500" height="400" alt="image" src="https://github.com/user-attachments/assets/8dd1e499-139f-4294-ae68-5692e971d20f" />
<img width="500" height="300" alt="image" src="https://github.com/user-attachments/assets/b9991910-f102-4cab-bf00-73b0f82cf9dd" />
<img width="500" height="300" alt="image" src="https://github.com/user-attachments/assets/09175a36-c404-4118-8ed7-efc2502f5529" />

The first plot shows that most drugs contain only one active ingredient, with fewer combination formulations containing multiple ingredients. The second plot highlights that certain ingredients appear across many different products, indicating that multiple marketed drugs share the same active ingredients. The third plot is a proof-of-concept similarity visualization, where drugs positioned close together share more similar ingredient compositions, suggesting structural equivalence or near equivalence despite different product names.

## 3. Usage scenarios

### Scenario 1 – Consumer choosing a cold medication

Peter has a cold and is experiencing a runny nose. At the pharmacy, he sees multiple Tylenol products on the shelf and is unsure which one to choose. “Tylenol Sinus” seems appropriate for his symptoms, but he wants to quickly confirm what it contains. Using the dashboard, he searches for the product name and views its active ingredients and dosage. He discovers that the pharmacy’s generic version contains the exact same ingredients and dosage at a lower price. Confident in the equivalence, he chooses the generic option and saves money.

### Scenario 2 – Pharmacist explaining generic equivalence

A customer asks for Tylenol, but the brand-name product is out of stock. The pharmacist suggests a generic alternative, explaining that it contains the same active ingredient and dosage. The customer is hesitant because the packaging looks unfamiliar. The pharmacist uses the dashboard to search for the drug and shows the relationship visualization panel, which clearly maps both products to the same active ingredient and strength. Seeing the visual confirmation, the customer feels reassured and agrees to purchase the generic version.

### Scenario 3 – Comparing similar products from different companies

A customer is deciding between two similar medications produced by different companies. Unsure whether they differ in formulation or dosage, the customer uses the dashboard to compare both products side by side. The third panel displays their active ingredients, strengths, and any additional components, allowing the user to identify whether the products are equivalent or if one includes extra ingredients that may not be necessary for their needs. This supports a more informed and cost-effective purchasing decision.


Below is a sketch of the dashboard:
<img width="1323" height="878" alt="image" src="https://github.com/user-attachments/assets/93f8a3d4-6d8f-48d9-9a5e-2e599ff712f4" />




