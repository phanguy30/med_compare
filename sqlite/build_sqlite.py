import os
import pandas as pd
from sqlalchemy import create_engine, text

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PSWD = os.getenv("MYSQL_PSWD", "")
MYSQL_DB   = os.getenv("MYSQL_DB", "rxnorm")

mysql_engine = create_engine(
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PSWD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
)

sqlite_engine = create_engine("sqlite:///rxnorm.sqlite")

# 1) RXNCONSO subset 
rxnconso = pd.read_sql(text("""
    SELECT RXCUI, STR, TTY, LAT
    FROM RXNCONSO
    WHERE TTY IN ('DP','SCDC','DF','MIN')
"""), mysql_engine)

# 2) RXNREL subset 
rxnrel = pd.read_sql(text("""
    SELECT RXCUI1, RXCUI2, RELA
    FROM RXNREL
    WHERE RELA IN ('has_ingredient', 'constitutes', 'has_doseform', 'has_doseform_of', 'consists_of')
"""), mysql_engine)

# Write to SQLite
rxnconso.to_sql("RXNCONSO", sqlite_engine, if_exists="replace", index=False)
rxnrel.to_sql("RXNREL", sqlite_engine, if_exists="replace", index=False)

print("Wrote rxnorm.sqlite")
print("RXNCONSO rows:", len(rxnconso))
print("RXNREL rows:", len(rxnrel))