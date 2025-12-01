import pandas as pd
import re
import socket
import glob
import os
import json
import dotenv
from datetime import datetime
import logging
from . import db

logger = logging.getLogger(__name__)

dotenv.load_dotenv(".env")


def write_log(msg):
    with open("log.txt", "a") as f:
        f.write(msg + "\n")


def is_valid_email(email):
    """Verifica se l'email ha un formato valido."""
    logger.info(f"Validating email: {email}")
    if pd.isnull(email) or pd.isna(email):
        return False
    else:
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        return re.match(pattern, email) is not None


def is_domain_reachable(email):
    """Verifica se il dominio dell'email è raggiungibile tramite DNS."""
    logger.info(f"Checking domain reachability for email: {email}")
    try:
        domain = email.split("@")[1]
        if socket.gethostbyname(domain):
            return True
    except Exception as e:
        logger.error(f"DNS: Errore: {e}, Dominio: {domain}")
        write_log(f"DNS: Errore: {e}, Dominio: {domain}")
        return False


def suggest_email_fix(email, common_domains=None):
    """Prova a correggere errori comuni nelle email."""
    logger.info(f"Suggesting email fix for: {email}")
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
    logger.info(f"Extracting domain from URL: {url}")
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
    logger.info(f"Removing province from city: {city}")
    try:
        return re.sub(r"\b[A-Z]{2}\b", "", city).strip()
    except Exception as e:
        logger.error(f"Error removing province from city: {city}, error: {e}")
        return city


def split_city_cap(df):
    """Separa la città dal CAP."""
    if "City" in df.columns:
        df["CAP"] = pd.StringDtype()
        df["Province"] = pd.StringDtype()
        for index, row in df.iterrows():
            if isinstance(row["City"], str):
                cap_match = re.search(r"(\d{4,5})", row["City"])
                province_match = re.search(r"\b([A-Z]{2})\b", row["City"])
                if province_match:
                    df.at[index, "Province"] = province_match.group(1)
                    df.at[index, "City"] = (
                        row["City"].replace(province_match.group(1), "").strip()
                    )
                else:
                    df.at[index, "Province"] = None
                if cap_match:
                    df.at[index, "CAP"] = cap_match.group(1)
                    df.at[index, "City"] = (
                        row["City"].replace(cap_match.group(1), "").strip()
                    )
                else:
                    df.at[index, "CAP"] = None
            else:
                df.at[index, "CAP"] = None
                df.at[index, "City"] = row["City"]
                df.at[index, "Province"] = None
    return df


def parse_xls(file_path):

    df = pd.read_excel(
        file_path,
        engine="openpyxl",
    )
    logger.info(f"Parsing file: {file_path}")
    logger.info("Normalizzazione colonne")

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
    else:
        df = df.rename(
            columns={
                "Valore": "Email",
                "Telefono2": "Cell",
                "Nome": "Name_or_Email",
                "Fonte": "Website",
                "Parole chiave": "Description",
                "Titolo": "Name",
                "META Description": "Meta Description",
                "META Keywords": "Meta Keywords",
                "Dominio": "Domain-1",
                "Paese": "Domain",
                "Cittа": "Country",
                "Indirizzo": "City",
                "Categoria": "Address",
                "Unnamed: 14": "Category-I",
                "Unnamed: 15": "Category-II",
            }
        )

    # Remove all unnamed columns
    unnamed_cols = [col for col in df.columns if col.startswith('Unnamed:')]
    if unnamed_cols:
        logger.info(f"Dropping unnamed columns: {unnamed_cols}")
        df.drop(columns=unnamed_cols, inplace=True)
    logger.info(f"Columns: {df.columns}")
    logger.info("Drop non italiani")
    df = df[df["Country"].str.lower() == "italy"]
    logger.info("Split città e CAP")
    df = split_city_cap(df)
    logger.info("Normalizzazione email")
    if "Email" not in df.columns:
        raise ValueError(f"Il file {file_path} non contiene una colonna 'Email'")
    df["Email"] = df["Email"].astype(str).str.strip().str.lower()

    # df["Email"] = df["Email"].strip().lower()
    logger.info("Estrazione dominio")
    df["Domain-1"] = df["Domain"].apply(
        lambda x: extract_domain(x) if not pd.isnull(x) or pd.isna(x) else None
    )
    logger.info("Suggerimento email corretta")
    df["Email Corretta"] = df["Email"].apply(
        lambda x: (suggest_email_fix(x, df["Domain-1"]) if not is_valid_email(x) else x)
    )
    logger.info("Verifica email")
    df["Email Valida"] = df["Email Corretta"].apply(lambda x: is_valid_email(x))
    logger.info("Verifica dominio raggiungibile")
    df["Dominio Raggiungibile"] = df["Email"].apply(
        lambda x: is_domain_reachable(x) if is_valid_email(x) else False
    )

    return df


def save_files(filename):
    """Salva il CSV non ripulito e il CSV ripulito."""
    try:
        os.mkdir("output_csv")
        os.mkdir("output_raw_csv")
    except FileExistsError:
        pass
    # for f in file_paths:
    df = parse_xls(filename)
    logger.info("Pulizia dati")
    logger.debug(f"Initial rows: {df.head()}")
    df_cleaned = df.dropna(subset=["Email Valida", "Dominio Raggiungibile"])
    df_cleaned = df_cleaned[
        df_cleaned["Email Valida"] & df_cleaned["Dominio Raggiungibile"]
    ]
    raw_entries = len(df)
    raw_output_path = os.path.join(
        "output_raw_csv", os.path.basename(filename.replace(".xlsx", "_raw.csv"))
    )
    df.to_csv(raw_output_path, index=False)
    cleaned_entries = len(df_cleaned)
    clean_output_path = os.path.join(
        "output_csv", os.path.basename(filename.replace(".xlsx", "_cleaned.csv"))
    )
    df_cleaned.to_csv(clean_output_path, index=False)
    logger.info(f"File: {filename}, Righe: {raw_entries}, Righe Pulite: {cleaned_entries}")
    with open("file_log.txt", "a") as f:
        f.write(f"File: {filename}, Righe: {raw_entries}, Righe Pulite: {cleaned_entries}\n")
    return clean_output_path


# Funzione per verificare e aggiornare la City
def verify_and_update_city(row, cap_dict):
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


def clean_data(table_id, filename):
    # file_list = glob.glob(upload_path+"/*.xlsx")
    file_path = "./daPulire/" + filename
    clean_output_path = save_files(file_path)
    with open("file_log.txt", "r") as f:
        count = 0
        lines = f.readlines()
        for line in lines:
            old = line.split(",")[1].split(":")[1].strip()
            new = line.split(",")[2].split(":")[1].strip()
            count = count + (int(old) - int(new))
        logger.info(f"Righe totali rimosse: {count}")
    # for f in file_list:
    os.remove(file_path)
    # file_list = glob.glob("./output_csv/*.csv")
    # all_data = []
    # for f in file_list:
    df = pd.read_csv(clean_output_path, engine="python", encoding="utf-8", dtype=str)
    # all_data.append(df)
    # all_df = pd.concat(all_data, ignore_index=True)

    for columns in df.columns:
        df[columns] = df[columns].fillna("")
    df = df.astype(str)
    df["Category"] = df["Category-I"] + df["Category-II"]
    df = df.drop(columns=["Category-I", "Category-II"])

    cap_df = pd.read_csv(
        "gi_comuni_cap.csv", sep=";", engine="python", encoding="utf-8", dtype=str
    )
    logger.info("Loaded city and CAP data")
    cap_df["comune"] = cap_df["denominazione_ita"].str.lower()
    cap_dict = cap_df.set_index("cap")["denominazione_ita"].to_dict()
    cap_comune = cap_df.set_index("cap")["comune"].to_dict()

    # Applica la funzione al DataFrame
    df["City"] = df.apply(verify_and_update_city, axis=1, args=(cap_dict,))
    df["CAP"] = df.apply(verify_and_update_cap, axis=1)
    df["Address"] = df["Address"].apply(lambda x: re.sub(r"\d{5}", "", str(x)).strip())
    logger.info("Uppercase province")
    df["Province"] = df["Province"].astype(str).str.upper()
    logger.info("Capitalizing city names")
    df["City"] = df["City"].astype(str).str.capitalize()
    filename = (
        "puliti/"
        + filename.replace(".xlsx", "_clean_")
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + ".csv"
    )

    # Remove all unnamed columns
    unnamed_cols = [col for col in df.columns if col.startswith('Unnamed:')]
    if unnamed_cols:
        logger.info(f"Dropping unnamed columns: {unnamed_cols}")
        df.drop(columns=unnamed_cols, inplace=True)
    logger.debug(f"Columns after dropping: {df.columns}")
    df.to_csv(filename, index=False)
    logger.info(f"File salvato: {filename}")
    db.save_to_table(table_id, df)
