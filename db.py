import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Carica le variabili d'ambiente
TOKEN = os.getenv("TOKEN")

# Salvataggio in nocodb
NC_DATA_URL = "http://nocodb:8080/api/v2/tables"
NC_META_URL = "http://nocodb:8080/api/v2/meta"

headers = {
    "Content-Type": "application/json",
    "xc-token": TOKEN,
}


def save_to_nocodb(all_df, filename):
    """Salva il DataFrame in NocoDB."""
    # Converti il DataFrame in un dizionario
    data = all_df.to_dict(orient="records")
    response = requests.post(NC_DATA_URL, headers=headers, json=data)
    print(response.json())
    print(f"File salvato in nocodb: {filename}")


def save_to_table(table_id: str, all_df: pd.DataFrame):
    """Salva il DataFrame in una tabella specifica di NocoDB."""
    # Converti il DataFrame in un dizionario
    print(table_id, all_df.head())
    data = all_df.to_dict(orient="records")
    print(f"{NC_DATA_URL}/{table_id}/records")
    response = requests.post(
        f"{NC_DATA_URL}/{table_id}/records", headers=headers, json=data
    )
    if response.status_code == 200:
        print(f"File salvato in NocoDB: {table_id}")
    else:
        print(f"Errore nel salvataggio in NocoDB: {response.status_code}")


def get_all_tables(base_id):
    """Recupera tutte le tabelle da NocoDB."""
    response = requests.get(f"{NC_META_URL}/bases/{base_id}/tables", headers=headers)
    if response.status_code == 200:
        tables = response.json().get("list", [])

        return tables
    else:
        print(f"Errore nel recupero delle tabelle: {response.status_code}")
        return None


def get_table(table_id):
    """Recupera una tabella specifica da NocoDB."""
    response = requests.get(f"{NC_DATA_URL}/{table_id}", headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Errore nel recupero della tabella: {response.status_code}")
        return None


def create_table(base_id, table_name):
    """Crea una nuova tabella in NocoDB."""
    CREATE_TABLE_URL = f"{NC_META_URL}/bases/{base_id}/tables"
    data = {
        "title": table_name,
        "table_name": table_name,
        "columns": [
            {
                "title": "ID",
                "uidt": "ID",
                "pv": True,
            },
            {
                "title": "Created At",
                "uidt": "CreatedTime",
            },
            {
                "title": "Updated At",
                "uidt": "UpdatedTime",
            },
            {
                "title": "Source",
                "uidt": "SingleLineText",
            },
            {
                "title": "Email",
                "uidt": "Email",
            },
            {
                "title": "Cell",
                "uidt": "PhoneNumber",
            },
            {
                "title": "Name_or_Email",
                "uidt": "SingleLineText",
            },
            {
                "title": "Website",
                "uidt": "URL",
            },
            {
                "title": "Description",
                "uidt": "LongText",
            },
            {
                "title": "Name",
                "uidt": "SingleLineText",
            },
            {
                "title": "Meta Description",
                "uidt": "SingleLineText",
            },
            {
                "title": "Meta Keywords",
                "uidt": "SingleLineText",
            },
            {
                "title": "Domain-1",
                "uidt": "URL",
            },
            {
                "title": "Domain",
                "uidt": "URL",
            },
            {
                "title": "Country",
                "uidt": "SingleLineText",
            },
            {
                "title": "City",
                "uidt": "SingleLineText",
            },
            {
                "title": "Address",
                "uidt": "SingleLineText",
            },
            {
                "title": "Category-I",
                "uidt": "SingleLineText",
            },
            {
                "title": "Category-II",
                "uidt": "SingleLineText",
            },
        ],
    }
    response = requests.post(CREATE_TABLE_URL, headers=headers, json=data)
    if response.status_code == 200:
        print(f"Tabella creata: {table_name}")
    else:
        print(f"Errore nella creazione della tabella: {response.status_code}")


def get_bases():
    """Recupera tutte le basi da NocoDB."""

    response = requests.get(f"{NC_META_URL}/bases/", headers=headers)
    if response.status_code == 200:
        bases = response.json().get("list", [])
        ids = []
        if bases:
            for base in bases:
                ids.append({"id": base["id"], "title": base["title"]})
            print(f"Basi trovate: {ids}")
        return ids
    else:
        print(f"Errore nel recupero delle basi: {response.status_code}")
        return None


if __name__ == "__main__":
    bases = get_bases()
    if bases:
        for base_id, base_name in bases:
            print(base_id, base_name)
