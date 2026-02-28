


-- querying a drug with a particular name, the rxcui is used to query the ingredients: some drugs to try Claritin-D (2 Ingredients), Tylenol PM (2 Ingredients), Excedrin (3 ingredients)
SELECT DISTINCT rxcui,rxaui, str AS display_name
FROM RXNCONSO
WHERE LOWER(str) LIKE LOWER('%Robitussin%')
and tty in ('SBD',"SCD", "DP");

-- getting a list of ingredients (active, inactive)- use rxaui 12750645 (AUI NOT CUI)
SELECT distinct r.rxaui2 AS rxcui, str, r.rela, c2.tty
FROM RXNREL r
JOIN RXNCONSO c2 ON c2.rxaui = r.rxaui2
WHERE r.rxaui1 = 12750645;
    



-- querying the ingredients + dose use rxcui = 198440
SELECT distinct r.rxcui2 AS rxcui, str, r.rela, c2.tty
FROM RXNREL r
JOIN RXNCONSO c2 ON c2.rxcui = r.rxcui2
WHERE r.rxcui1 = 198440
  AND r.rela = 'constitutes'
  AND c2.sab = 'RXNORM'
  and tty = 'SCDC';
  


-- querying for all drugs that have these one of these exact ingredient with the same dose
-- do the same for the all the ingredients then intersection in python\
-- SCD is the generic version, SBD is the branded options

select distinct r2.rxcui, r2.str, r1.rela, r2.tty
from rxnrel r1 join rxnconso r2 on r1.rxcui2 = r2.rxcui
where rxcui1 = 315266 and r2.sab = "RXNORM" and tty in ('SBD',"SCD") and rela = "consists_of";

select distinct r2.rxcui, r2.str, r1.rela, r2.tty
from rxnrel r1 join rxnconso r2 on r1.rxcui2 = r2.rxcui
where rxcui1 = 1112247 and r2.sab = "RXNORM" and tty in ('SBD',"SCD")and rela = "consists_of";



-- So uses the RXCUI of the ingredient 315266 + dose you can get just the ingredient name without the dose - - rxcui 161
SELECT distinct r.rxcui2, r.rxaui2, str, r.rela, c2.tty
FROM RXNREL r
JOIN RXNCONSO c2 ON c2.rxcui = r.rxcui2
WHERE r.rxcui1 = 315266 and rela = 'ingredient_of'
limit 1;

-- Basically how it works is that drug -> components with dose(through rela "constitutes")-> 
-- singular components by themselves ("through rela: "has_ingredients", "part_of")-> 
-- This query is to find all drugs that somewhat similar to the drug of interest
-- inner queries give rxcui of ingredient combinations that contain acetminophen
-- outer queries get any drugs that contain these combiinations
-- then return drugs that contain those components
SELECT DISTINCT
  d.rxcui,
  d.str,
  d.tty,
  r1.rela
FROM (
  SELECT DISTINCT r.rxcui1 AS comp_rxcui
  FROM RXNREL r
  WHERE r.rxcui2 = 161
    AND r.rela IN ('ingredient_of', 'part_of')
) comps -- this gets a list of components that contain acetaminophen 161
JOIN RXNREL r1
  ON r1.rxcui2 = comps.comp_rxcui          -- get drugs that contain these components
 AND r1.rela IN ('consists_of','constitutes','has_ingredients')
JOIN RXNCONSO d								-- join to conso to get drug name
  ON d.rxcui = r1.rxcui1                  
WHERE d.tty IN ('SBD','SCD');
   






         



