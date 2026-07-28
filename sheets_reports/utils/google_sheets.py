import time

import gspread
import pandas as pd
from django.conf import settings
from django.core.cache import cache
from google.oauth2.service_account import Credentials


# Alcances necesarios para leer hojas de Google
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

# Rate limiter sliding window global (compartido entre workers vía DatabaseCache).
# Garantiza que en cualquier ventana real de 60s no se superen las 55 llamadas,
# independientemente de cuántos dashboards, sesiones o workers haya.
_GSHEETS_LIMIT = 55
_GSHEETS_WINDOW = 60


def _wait_gsheets_slot():
    """Bloquea hasta conseguir un slot en la ventana deslizante de 60s."""
    key = "gsheets_ts"
    lock_key = "gsheets_ts_lock"

    while True:
        now = time.monotonic()
        ts = cache.get(key) or []
        ts = [t for t in ts if now - t < _GSHEETS_WINDOW]
        if len(ts) >= _GSHEETS_LIMIT:
            time.sleep(min(3, ts[0] + _GSHEETS_WINDOW - now))
            continue

        if cache.add(lock_key, True, 5):
            try:
                ts = cache.get(key) or []
                ts = [t for t in ts if now - t < _GSHEETS_WINDOW]
                if len(ts) >= _GSHEETS_LIMIT:
                    continue
                ts.append(now)
                cache.set(key, ts, _GSHEETS_WINDOW * 2)
                return
            finally:
                cache.delete(lock_key)
        time.sleep(0.05)


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
    generate_widget_ia._build_sheets_context), sin que el usuario tenga que nombrar la pestaña en su
    descripción, y sin el costo de traer cada pestaña completa como hace fetch_sheet_as_dataframe.

    Retorna { "<título de pestaña>": {"columns": [...], "sample_rows": [{col: valor, ...}, ...]} }.
    """
    creds = get_credentials()
    client = gspread.authorize(creds)

    _wait_gsheets_slot()
    spreadsheet = client.open_by_url(source_url)

    _wait_gsheets_slot()
    titles = [ws.title for ws in spreadsheet.worksheets()]
    if not titles:
        return {}

    ranges = []
    for title in titles:
        escaped_title = title.replace("'", "''")
        ranges.append(f"'{escaped_title}'!1:{n_rows + 1}")
    _wait_gsheets_slot()
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


def fetch_all_sheets_as_dataframes(source_url: str) -> dict[str, pd.DataFrame]:
    """
    Trae, en una sola llamada a la API (values_batch_get), los datos COMPLETOS de TODAS las
    pestañas del spreadsheet. Se usa para el refresco en background (management command
    refresh_sheets_cache): reemplaza lo que de otra forma serían N llamadas a
    fetch_sheet_as_dataframe (una por pestaña) por 1 sola, sin importar cuántas pestañas
    tenga el spreadsheet -- así un refresco completo cuesta 2 llamadas (open_by_url +
    values_batch_get) en vez de 2+N.

    Los valores vienen como strings crudos (sin la coerción de tipos de get_all_records),
    lo cual no afecta nada río abajo porque duckdb_query.py ya crea todas las columnas de
    Sheets como VARCHAR.

    Retorna { "<título de pestaña>": DataFrame }.
    """
    creds = get_credentials()
    client = gspread.authorize(creds)

    _wait_gsheets_slot()
    spreadsheet = client.open_by_url(source_url)

    _wait_gsheets_slot()
    titles = [ws.title for ws in spreadsheet.worksheets()]
    if not titles:
        return {}

    ranges = []
    for title in titles:
        escaped_title = title.replace("'", "''")
        ranges.append(f"'{escaped_title}'")
    _wait_gsheets_slot()
    response = spreadsheet.values_batch_get(ranges)

    dataframes = {}
    for title, value_range in zip(titles, response.get("valueRanges", [])):
        rows = value_range.get("values", [])
        if not rows:
            dataframes[title] = pd.DataFrame()
            continue
        columns = rows[0]
        data_rows = rows[1:]
        dataframes[title] = pd.DataFrame(
            [
                {col: (row[i] if i < len(row) else "") for i, col in enumerate(columns)}
                for row in data_rows
            ],
            columns=columns,
        )
    return dataframes


def fetch_sheet_as_dataframe(source_url: str, sheet_name: str | None = None) -> pd.DataFrame:
    """
    Conecta a una hoja de Google Sheets y retorna sus datos como DataFrame.
    La primera fila se usa como nombres de columnas.
    """
    creds = get_credentials()
    client = gspread.authorize(creds)

    # Abre la hoja por URL
    _wait_gsheets_slot()
    spreadsheet = client.open_by_url(source_url)

    # Si se especifica una hoja particular, úsala; si no, usa la primera
    worksheet = spreadsheet.worksheet(sheet_name) if sheet_name else spreadsheet.sheet1

    _wait_gsheets_slot()
    records = worksheet.get_all_records()
    if not records:
        _wait_gsheets_slot()
        header = worksheet.row_values(1)
        if header:
            return pd.DataFrame(columns=header)
        return pd.DataFrame()

    df = pd.DataFrame(records)
    return df
