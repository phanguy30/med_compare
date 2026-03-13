# Reflection — Med-Compare: Interactive Drug Identity & Comparison Dashboard
### Description of the Project

The goal of the Med-Compare dashboard was to help users better understand drug identity and formulation transparency using standardized pharmaceutical data from RxNorm. Many consumers encounter confusion when different brand names appear to represent distinct medications, when in reality they may share identical or highly similar ingredient compositions. Our project addresses this issue by providing a visual system that compares drugs based on their active ingredients rather than their marketing names.

The dashboard allows users to search for a drug and immediately view its ingredient composition, exact formulation matches, and alternative products with similar ingredients. This helps users understand whether different drugs are truly different or simply variations of the same formulation.

To make the system more intuitive, we implemented a Quick Samples layout that includes example drugs such as Tylenol and Excedrin. These buttons bypass the search process and instantly demonstrate the dashboard’s functionality. This feature was particularly useful for first-time users because it allows them to explore the visualization system without needing prior knowledge of specific drug names.

The interface was designed using a multi-panel layout that supports exploratory analysis. The Drug Information panel provides key information about the selected drug and its active ingredients. The Similarity Cluster view, generated using UMAP dimensionality reduction, visually groups drugs based on ingredient similarity and allows users to discover related products. The Ingredient Heatmap comparison enables direct comparison between drugs by showing which active ingredients are present across multiple products.

### Deployment
We used the Render platform to deploy our Med-Compare Dashboard. One fo the main issue we faced was the high computational cost of the Umaps, which could not be supported by the Free version of Render. So we improvised with the Quick Samples layout by precomputing the Umap for these particular drugs for the Deployed version of the project, while keeping the Search Functionality intact in the final github release versions. 

### Fixes mentioned by the TA
The TA mentioned some quick fixes for Milestone-3 that will make the Dashboard standout. The following is a list of such changes -
- Changed the Font and Style of the Drug Information Panel
- Maintained a consistent colour grading across all the plots. The colour we ended up choosing was blue.
- Aligned the Dashboard panels in such a way that it covers the full width while viewed in Full Screen. 
- Made the Interplot functionality between Umap and Heatmap look more polished (Colour and Font Styling changes)

### Conclusion
Overall, this project demonstrates how standardized medical data can be transformed into an interactive visualization tool that improves transparency in pharmaceutical products. By focusing on ingredient relationships rather than brand identity, the dashboard encourages users to better understand formulation similarities and potential alternatives.

### Future Improvements
Future improvements could include integrating pharmacologic class information from the RxClass API, expanding ingredient metadata, and improving clustering performance for larger drug datasets.