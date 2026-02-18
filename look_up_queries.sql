


-- querying a drug with a particular name, the rxcui is used to query the ingredients: some drugs to try Claritin-D (2 Ingredients), Tylenol PM (2 Ingredients), Excedrin (3 ingredients)
SELECT DISTINCT rxcui, str AS display_name
FROM RXNCONSO
WHERE LOWER(str) LIKE LOWER('%Excedrin%')
and tty in ('SBD',"SCD")
and sab = "RXNORM"
LIMIT 100; 


-- querying the ingredients 
SELECT distinct r.rxcui2 AS rxcui, str, r.rela, c2.tty
FROM RXNREL r
JOIN RXNCONSO c2 ON c2.rxcui = r.rxcui2
WHERE r.rxcui1 = 209468
  AND r.rela = 'constitutes'
  AND c2.sab = 'RXNORM'
  and tty = 'SCDC';
  


-- querying for all drugs that have these one of the indreidents 
-- do the same for the all the ingredients then intersection in python\
-- SCD is the generic version, SBD is the branded options

select distinct r2.rxcui, r2.str, r1.rela, r2.tty
from rxnrel r1 join rxnconso r2 on r1.rxcui2 = r2.rxcui
where rxcui1 = 317311 and r2.sab = "RXNORM" and tty in ('SBD',"SCD") and rela = "consists_of";

select distinct r2.rxcui, r2.str, r1.rela, r2.tty
from rxnrel r1 join rxnconso r2 on r1.rxcui2 = r2.rxcui
where rxcui1 = 1112247 and r2.sab = "RXNORM" and tty in ('SBD',"SCD")and rela = "consists_of";











   





         



