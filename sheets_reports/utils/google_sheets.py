import gspread
import pandas as pd
from django.conf import settings
from google.oauth2.service_account import Credentials


# Alcances necesarios para leer hojas de Google
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


def get_credentials():
    """Retorna las credenciales de service account desde el JSON configurado."""
    path = settings.GOOGLE_SHEETS_CREDENTIALS_PATH
    if not path:
        raise ValueError(
            "GOOGLE_SHEETS_CREDENTIALS_PATH no está configurado en .env"
        )
    return Credentials.from_service_account_file(path, scopes=SCOPES)


def list_worksheet_titles(source_url: str) -> list[str]:
    """Retorna los títulos de todas las pestañas del spreadsheet."""
    creds = get_credentials()
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_url(source_url)
    return [ws.title for ws in spreadsheet.worksheets()]


def fetch_sheet_as_dataframe(source_url: str, sheet_name: str | None = None) -> pd.DataFrame:
    """
    Conecta a una hoja de Google Sheets y retorna sus datos como DataFrame.
    La primera fila se usa como nombres de columnas.
    """
    creds = get_credentials()
    client = gspread.authorize(creds)

    # Abre la hoja por URL
    spreadsheet = client.open_by_url(source_url)

    # Si se especifica una hoja particular, úsala; si no, usa la primera
    worksheet = spreadsheet.worksheet(sheet_name) if sheet_name else spreadsheet.sheet1

    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    return df
