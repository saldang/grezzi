import pandas as pd
import re
import socket
import glob
import os
import requests
import json
import dotenv
from datetime import datetime

dotenv.load_dotenv(".env")

def write_log(msg):
    with open("log.txt", "a") as f:
        f.write(msg + "\n")


def is_valid_email(email):
    """Verifica se l'email ha un formato valido."""
    if pd.isnull(email) or pd.isna(email):
        return False
    else:
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        return re.match(pattern, email) is not None


def is_domain_reachable(email):
    """Verifica se il dominio dell'email è raggiungibile tramite DNS."""
    try:
        domain = email.split("@")[1]
        if socket.gethostbyname(domain):
            return True
    except Exception as e:
        write_log(f"DNS: Errore: {e}, Dominio: {domain}")
        return False


def suggest_email_fix(email, common_domains=None):
    """Prova a correggere errori comuni nelle email."""
    if "@" not in email:
        return None
    username, domain = email.split("@", 1)
    domain = domain.lower().strip()

    for common in common_domains:
        if not pd.isna(common):
            if domain.startswith(common[:3]):
                return f"{username}@{common}"
        else:
            continue
    return None


def extract_domain(url):
    """Estrae la parte del dominio da un URL."""
    if pd.isnull(url) or pd.isna(url):
        return None
    else:
        pattern = r"(www\.)?([^/]+)"
        match = re.search(pattern, url)
        if match:
            return match.group(2)
        else:
            return url

def remove_province(city):
    """Rimuove la provincia dalla città."""
    try:
        return re.sub(r"\b[A-Z]{2}\b", "", city).strip()
    except Exception as e:
        return city

def split_city_cap(df):
    """Separa la città dal CAP."""
    if "City" in df.columns:
        df["CAP"] = pd.StringDtype()
        df["CAP"] = df["City"].str.extract(r"(\d{4,5})")
        df["CAP"] = df["CAP"].str.strip()

        df["City"] = df["City"].str.replace(r"\d{4,5}\s*", "", regex=True)
        df["Province"] = pd.StringDtype()
        df["Province"] = df["City"].str.extract(r"\b([A-Z]{2})\b")
        df["Province"] = df["Province"].str.strip()
        df["City"] = df["City"].apply(remove_province)

    return df


def parse_xls(file_path):

    df = pd.read_excel(
        file_path,
        engine="openpyxl",
    )
    print(file_path)
    print("Normalizzazione colonne")
    if "Value" in df.columns:
        df = df.rename(
            columns={
                "Value": "Email",
                "Phone2": "Phone",
                "Name": "Name_or_Email",
                "Source": "Website",
                "Keywords": "Description",
                "Title": "Name",
                "META Description": "Meta Description",
                "META Keywords": "Meta Keywords",
                "Domain": "Domain-1",
                "Country": "Domain",
                "City": "Country",
                "Address": "City",
                "Category": "Address",
                "Unnamed: 14": "Category-I",
                "Unnamed: 15": "Category-II",
            }
        )
    # else:
    #     df = df.rename(
    #         columns={
    #             "Valore": "Email",
    #             "Telefono2": "Cell",
    #             "Nome": "Name_or_Email",
    #             "Fonte": "Website",
    #             "Parole chiave": "Description",
    #             "Titolo": "Name",
    #             "META Description": "Meta Description",
    #             "META Keywords": "Meta Keywords",
    #             "Dominio": "Domain-1",
    #             "Paese": "Domain",
    #             "Cittа": "Country",
    #             "Indirizzo": "City",
    #             "Categoria": "Address",
    #             "Unnamed: 14": "Category-I",
    #             "Unnamed: 15": "Category-II",
    #         }
    #     )
    print(df.columns)
    print("Drop non italiani")
    df = df[df["Country"].str.lower() == "italy"]
    print("Split città e CAP")
    df = split_city_cap(df)
    print("Normalizzazione email")
    if "Email" not in df.columns:
        raise ValueError(f"Il file {file_path} non contiene una colonna 'Email'")
    df["Email"] = df["Email"].astype(str).str.strip().str.lower()

    # df["Email"] = df["Email"].strip().lower()
    print("Estrazione dominio")
    df["Domain-1"] = df["Domain"].apply(
        lambda x: extract_domain(x) if not pd.isnull(x) or pd.isna(x) else None
    )
    print("Suggerimento email corretta")
    df["Email Corretta"] = df["Email"].apply(
        lambda x: (suggest_email_fix(x, df["Domain-1"]) if not is_valid_email(x) else x)
    )
    print("Verifica email")
    df["Email Valida"] = df["Email Corretta"].apply(lambda x: is_valid_email(x))
    print("Verifica dominio raggiungibile")
    df["Dominio Raggiungibile"] = df["Email"].apply(
        lambda x: is_domain_reachable(x) if is_valid_email(x) else False
    )

    return df


def save_files(file_paths):
    """Salva il CSV non ripulito e il CSV ripulito."""
    try:
        os.mkdir("output_csv")
        os.mkdir("output_raw_csv")
    except FileExistsError:
        pass
    for f in file_paths:
        df = parse_xls(f)
        df_cleaned = df.dropna(subset=["Email Valida", "Dominio Raggiungibile"])
        df_cleaned = df_cleaned[
            df_cleaned["Email Valida"] & df_cleaned["Dominio Raggiungibile"]
        ]
        raw_entries = len(df)
        raw_output_path = os.path.join(
            "output_raw_csv", os.path.basename(f.replace(".xlsx", "_raw.csv"))
        )
        df.to_csv(raw_output_path, index=False)
        cleaned_entries = len(df_cleaned)
        clean_output_path = os.path.join(
            "output_csv", os.path.basename(f.replace(".xlsx", "_cleaned.csv"))
        )
        df_cleaned.to_csv(clean_output_path, index=False)
        print(f"File: {f}, Righe: {raw_entries}, Righe Pulite: {cleaned_entries}")
        print(
            f"File: {f}, Righe: {raw_entries}, Righe Pulite: {cleaned_entries}",
            file=open("file_log.txt", "a"),
        )


# Funzione per verificare e aggiornare la City
def verify_and_update_city(row):
    cap = row["CAP"]
    city = row["City"]
    correct_city = cap_dict.get(cap)
    if correct_city and city != correct_city:
        return correct_city
    else:
        return city


def verify_and_update_cap(row):
    cap = row["CAP"]
    if not cap:
        c = re.search(r"\d{5}", str(row["Address"]))
        if c is not None:
            cap = c.group(0)

    return cap


if __name__ == "__main__":
    file_list = glob.glob("daPulire/*.xlsx")
    save_files(file_list)

    with open("file_log.txt", "r") as f:
        count = 0
        lines = f.readlines()
        for line in lines:
            old = line.split(",")[1].split(":")[1].strip()
            new = line.split(",")[2].split(":")[1].strip()
            count = count + (int(old) - int(new))
        print(f"Righe totali rimosse: {count}")
    for f in file_list:
        os.remove(f)
    file_list = glob.glob("./output_csv/*.csv")
    all_data = []
    for f in file_list:
        df = pd.read_csv(f, engine="python", encoding="utf-8", dtype=str)
        all_data.append(df)
    all_df = pd.concat(all_data, ignore_index=True)

    for columns in all_df.columns:
        all_df[columns] = all_df[columns].fillna("")
    all_df = all_df.astype(str)
    all_df["Category"] = all_df["Category-I"] + all_df["Category-II"]
    all_df = all_df.drop(columns=["Category-I", "Category-II"])

    cap_df = pd.read_csv(
        "gi_comuni_cap.csv", sep=";", engine="python", encoding="utf-8", dtype=str
    )
    cap_df["comune"] = cap_df["denominazione_ita"].str.lower()
    cap_dict = cap_df.set_index("cap")["denominazione_ita"].to_dict()
    cap_comune = cap_df.set_index("cap")["comune"].to_dict()

    # Applica la funzione al DataFrame
    all_df["City"] = all_df.apply(verify_and_update_city, axis=1)
    all_df["CAP"] = all_df.apply(verify_and_update_cap, axis=1)
    all_df["Address"] = all_df["Address"].apply(
        lambda x: re.sub(r"\d{5}", "", x).strip()
    )
    all_df["Province"] = all_df["Province"].str.upper()
    all_df["City"] = pd.StringDtype()
    all_df["City"] = all_df["City"].str.capitalize()
    filename = "puliti/all_data" + datetime.now().strftime("%Y%m%d%H%M%S") + ".csv"
    if "Unnamed: 13" in all_df.columns:
        all_df.drop(columns=["Unnamed: 13"])
    if "Unnamed: 16" in all_df.columns:
        all_df.drop(columns=["Unnamed: 16"])
    all_df.to_csv(filename, index=False)

    TABLE_ID = os.getenv("TABLE_ID")
    TOKEN = os.getenv("TOKEN")
    # Salvataggio in nocodb
    NODODB_URL = f"http://nocodb:8080/api/v2/tables/{TABLE_ID}/records"

    # Inserimento all_df in nocodb


    headers = {
        "Content-Type": "application/json",
        "xc-token": TOKEN,
    }

    data = all_df.to_dict(orient="records")
    print(data)
    response = requests.post(NODODB_URL, headers=headers, json=data)
    print(response.json())
    print(f"File salvato in nocodb: {filename}")
