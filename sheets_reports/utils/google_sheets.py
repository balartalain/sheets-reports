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


def fetch_sheets_preview(source_url: str, n_rows: int = 3) -> dict[str, dict]:
    """
    Trae, en una sola llamada a la API (values_batch_get), la estructura de TODAS las pestañas
    del spreadsheet: sus columnas (fila de encabezado) y las primeras `n_rows` filas de datos de
    cada una. Se usa para darle a Gemini visión completa del spreadsheet al generar código (ver
    gemini_client._build_sheets_context), sin que el usuario tenga que nombrar la pestaña en su
    descripción, y sin el costo de traer cada pestaña completa como hace fetch_sheet_as_dataframe.

    Retorna { "<título de pestaña>": {"columns": [...], "sample_rows": [{col: valor, ...}, ...]} }.
    """
    creds = get_credentials()
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_url(source_url)

    titles = [ws.title for ws in spreadsheet.worksheets()]
    if not titles:
        return {}

    ranges = []
    for title in titles:
        escaped_title = title.replace("'", "''")
        ranges.append(f"'{escaped_title}'!1:{n_rows + 1}")
    response = spreadsheet.values_batch_get(ranges)

    preview = {}
    for title, value_range in zip(titles, response.get("valueRanges", [])):
        rows = value_range.get("values", [])
        if not rows:
            preview[title] = {"columns": [], "sample_rows": []}
            continue
        columns = rows[0]
        preview[title] = {
            "columns": columns,
            "sample_rows": [
                {col: (row[i] if i < len(row) else "") for i, col in enumerate(columns)}
                for row in rows[1:]
            ],
        }
    return preview


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
