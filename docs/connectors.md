# Conectores de datos y capa de consulta DuckDB

Este documento explica la arquitectura que permite que un `Dashboard` obtenga sus datos de
distintos orígenes (Google Sheets, PostgreSQL, y en el futuro otros como MySQL) de forma
uniforme, y cómo agregar un origen nuevo.

## El problema que resuelve

Antes, `Dashboard.source_url` era un campo hardcodeado que asumía que el origen de datos
siempre era una hoja de Google Sheets. Todo el código de los widgets llamaba por convención a
`get_cached_df(widget.dashboard, sheet_name=...)`, que internamente abría la hoja por URL vía
`gspread` y devolvía un `pandas.DataFrame`. No existía ninguna abstracción de "origen de
datos": Sheets estaba entretejido directamente en el modelo, en la generación de código por IA
y en el código de cada widget.

## El patrón: Strategy + Registry

### 1. La interfaz común (`sheets_reports/connectors/base.py`)

`DataConnector` es la interfaz (ABC) que cumple cualquier origen de datos:

```python
class DataConnector(ABC):
    def __init__(self, config: dict): ...

    @classmethod
    @abstractmethod
    def config_schema(cls) -> type[BaseModel]:
        """Modelo pydantic que valida/coerciona DataSource.config para este tipo."""

    @abstractmethod
    def test_connection(self) -> None:
        """Levanta DataSourceConnectionError si la conexión no es válida."""

    @abstractmethod
    def list_tables(self) -> list[TableInfo]:
        """Tablas/pestañas disponibles, con columnas y filas de ejemplo (para IA/UI)."""

    @abstractmethod
    def register(self, con: duckdb.DuckDBPyConnection, alias: str) -> None:
        """Deja los datos de este origen consultables por SQL dentro de `con`."""
```

`register()` es el método clave: es lo que permite que DuckDB actúe como "lenguaje de consulta
genérico" sobre cualquier origen. Como Sheets y Postgres necesitan registrarse en DuckDB de
formas fundamentalmente distintas, hay dos mixins intermedios (segregación de interfaz: cada
tipo implementa solo lo que le corresponde):

- **`DataFrameBackedConnector`** — para orígenes sin motor SQL propio (Sheets, CSV, APIs).
  Trae los datos enteros como `pandas.DataFrame` y los expone con `con.register()`. Cada tabla
  queda como `"<alias>__<nombre_tabla>"`.
- **`SqlNativeConnector`** — para orígenes con motor SQL propio (Postgres, MySQL). Usa `ATTACH`
  de DuckDB para *federar* el servidor directamente: DuckDB empuja la consulta al servidor real
  (pushdown), nunca copia los datos a memoria. Las tablas quedan accesibles con el catálogo
  nativo adjuntado, ej. `postgres.public.ventas`.

### 2. El registro de tipos (`sheets_reports/connectors/registry.py`)

Un decorador llena un diccionario a nivel de módulo — el mismo idioma que ya usa
`sheets_reports/utils/registry.py` con `@util(...)` → `UTILS_REGISTRY` para las utilidades
inyectadas en el `exec()` de los widgets:

```python
CONNECTOR_REGISTRY: dict[str, type[DataConnector]] = {}

def connector(kind: str):
    def decorator(cls):
        CONNECTOR_REGISTRY[kind] = cls
        return cls
    return decorator
```

`get_connector(data_source)` instancia la clase correcta según `data_source.source_type`.
`ensure_loaded()` fuerza el import de los módulos que definen conectores (import diferido, para
evitar un ciclo con el propio archivo que define el decorador `connector`).

### 3. Las implementaciones concretas

- **`sheets_reports/connectors/google_sheets.py`** — `GoogleSheetsConnector`, envuelve el
  código que ya existía en `sheets_reports/utils/google_sheets.py` (gspread) sin reescribirlo.
- **`sheets_reports/connectors/postgres.py`** — `PostgresConnector`, arma un DSN de libpq
  (con escapado correcto de comillas) y lo usa en:

  ```sql
  ATTACH '<dsn>' AS <alias> (TYPE postgres, READ_ONLY)
  ```

  `READ_ONLY` está **hardcodeado, no es configurable**. Es la barrera de seguridad principal:
  el código de los widgets corre en un `exec()` sandboxeado pero no totalmente confiable (puede
  venir de una IA), así que si un widget generado intentara un `INSERT`/`UPDATE`/DDL, DuckDB lo
  rechaza antes de que llegue a Postgres.

## El modelo de datos (`sheets_reports/models.py`)

`DataSource` es un modelo nuevo, desacoplado de `Dashboard`, para poder reutilizar una misma
conexión entre varios tableros:

```python
class DataSource(models.Model):
    class SourceType(models.TextChoices):
        GOOGLE_SHEETS = "google_sheets", "Google Sheets"
        POSTGRES = "postgres", "PostgreSQL"

    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=30, choices=SourceType.choices)
    config = models.JSONField(default=dict)   # sheets: {"source_url": ...}; postgres: host/port/database/user/password/sslmode
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="data_sources")

    def get_connector(self) -> DataConnector:
        from sheets_reports.connectors.registry import get_connector
        return get_connector(self)
```

`Dashboard.data_source` es un FK a `DataSource` (`on_delete=PROTECT`, para que borrar una
`DataSource` compartida no borre tableros en cascada). El campo viejo `Dashboard.source_url` se
conservó (vacío, sin usarse) para no arriesgar una migración destructiva sobre datos de
producción sin tests; toda la lectura ya pasa por `data_source`.

Las migraciones (`0015_...` y `0016_backfill_datasource.py`) crean el modelo nuevo y migran
automáticamente cada `Dashboard` existente: por cada uno con `source_url` no vacío, se crea una
`DataSource(source_type="google_sheets")` equivalente y se la asigna.

## La capa DuckDB (`sheets_reports/utils/duckdb_query.py`)

Esta es la pieza que resuelve "lenguaje de consulta genérico": `get_query_connection(dashboard)`
abre una conexión DuckDB en memoria y llama a `connector.register(con, alias)`. El widget no
necesita saber si el origen es Sheets o Postgres — solo escribe SQL:

```python
con = get_query_connection(widget.dashboard)
df = con.execute("SELECT * FROM postgres.public.ventas WHERE region = ?", [valor]).df()
```

Se registró como `@util` (mismo mecanismo que `get_cached_df`), así queda disponible
automáticamente en el `exec()` de cualquier widget vía `get_system_namespace()`.

**Cacheo**: una conexión DuckDB viva no es cacheable (no es picklable, tiene sockets/handles
abiertos). Para Sheets, lo caro es el fetch a la API de Google — eso se sigue cacheando dentro
del connector (reutiliza el lock+TTL que ya existía en `get_cached_df`). Para Postgres no hay
nada análogo que cachear: `ATTACH` no trae datos, es un descriptor liviano que DuckDB usa para
empujar la consulta al servidor, así que se re-adjunta en cada llamada.

## Compatibilidad hacia atrás (`sheets_reports/utils/cache.py`)

`get_cached_df`/`get_cached_sheets_preview` (usadas por todos los widgets ya existentes, y ya
marcadas `[LEGACY]` en la descripción que ve la IA) ahora resuelven vía
`dashboard.data_source.get_connector()` en vez de `dashboard.source_url` directo, pero
mantienen las mismas cache keys y el mismo locking. Si se llaman sobre un dashboard cuyo origen
no es `DataFrameBackedConnector` (ej. un Postgres), levantan un error claro indicando que hay
que usar `get_query_connection` en su lugar.

## Prompt de IA (`sheets_reports/utils/generate_widget_ia.py`)

Hay un único `SYSTEM_INSTRUCTION_TEMPLATE`, igual para cualquier tipo de origen: siempre
enseña a usar `get_query_connection(widget.dashboard)` + SQL, nunca pandas + `get_cached_df`
(esa función queda marcada `[LEGACY]` en su descripción — ver más abajo — y solo se sigue
registrando para no romper widgets ya guardados de antes de este cambio). Al principio hubo
dos templates, uno por tipo de origen (Sheets seguía con pandas, solo Postgres usaba SQL) por
una decisión de minimizar riesgo sobre el único flujo en producción — pero eso contradecía el
objetivo de "lenguaje de consulta genérico", así que se unificó: `get_query_connection` ya
registraba las pestañas de Sheets en DuckDB igual que las tablas de Postgres, no había ninguna
razón técnica para la diferencia.

`_build_source_context(dashboard, prompt)` (antes `_build_sheets_context`, específica de
Sheets) se generalizó para usar `connector.list_tables()` — funciona igual para ambos orígenes,
mostrándole a la IA las tablas/columnas/filas de ejemplo disponibles.

**Bug encontrado y corregido durante la verificación de la unificación**: el nombre de tabla
que `_build_source_context` le mostraba a la IA (`TableInfo.name`, ej. `"Destinatarios"`) no
coincidía con el nombre realmente consultable en DuckDB (ej. `"google_sheets__Destinatarios"`,
con el prefijo que agrega `register()`). El prompt le decía a Gemini "usá el nombre EXACTO que
se muestra abajo", pero lo que se mostraba estaba mal — la IA a veces adivinaba bien el
prefijo (por el ejemplo genérico en las instrucciones) y a veces no, generando SQL que fallaba
con `Catalog Error: Table ... does not exist`. Se agregó `DataConnector.qualified_table_name(table,
alias)` (implementado en cada mixin: `f"{alias}__{table.name}"` para `DataFrameBackedConnector`,
`f"{alias}.{table.name}"` para `SqlNativeConnector`), y `_build_source_context` ahora muestra
ese nombre calificado, no el crudo — así lo que ve la IA es exactamente lo que hay que escribir
en el `FROM`.

**Segundo bug encontrado en la misma verificación**: `DataFrameBackedConnector.register()` (lo
que `get_query_connection` llama en cada ejecución de un widget) traía el DataFrame completo de
**todas** las pestañas del spreadsheet desde cero cada vez, sin ningún cacheo — a diferencia de
`get_cached_df`, que sí cacheaba. Con un spreadsheet de 18 pestañas, esto agotaba la cuota de
lectura de la API de Google Sheets (`429: Quota exceeded`) en minutos con solo un puñado de
ejecuciones. Se agregó cacheo (mismo `fetch_with_lock` de `utils/cache.py`, ahora expuesto sin
el prefijo `_`) dentro de `GoogleSheetsConnector.fetch_dataframe()` y `.list_tables()`, con
cache keys hasheadas (`hashlib.md5`) para no depender de que la URL/nombre de pestaña sea
válido como key literal (algunos backends de cache, ej. memcached, rechazan espacios y ciertos
caracteres). También se agregó `cache.get_cached_tables(dashboard)`, un cacheo genérico (para
cualquier tipo de origen) sobre `connector.list_tables()`, usado por `_build_source_context`
para no repetir la introspección completa una vez por cada widget cuando se genera un tablero
entero de punta a punta (`generate_dashboard_ia.generate_board_from_prompt`).

## Puente en la API (`sheets_reports/views_dashboard.py`)

El frontend actual (`home.html`) todavía solo sabe mandar `source_url` — no se tocó en esta
pasada. `_resolve_data_source(data, user, name_hint)` puentea esto:

- Si el request trae `source_url` (como hoy), crea una `DataSource` de tipo Sheets al vuelo.
- Si trae `data_source_id`, reutiliza una `DataSource` ya existente — el camino para usar una
  conexión Postgres, hoy dada de alta vía Django admin (`DataSourceAdmin`, en `admin.py`).

## Un detalle de seguridad del sandbox (`sheets_reports/utils/widget_dispatcher.py`)

El `exec()` de los widgets bloquea todos los imports salvo un whitelist explícito (no hay
`open`, `os`, `subprocess`, etc.). `con.execute(...).df()` de DuckDB dispara imports internos
de `collections.abc`/`numpy`/`pandas` en tiempo de llamada (igual que ya le pasaba a
`datetime`, que necesita `time`). El whitelist se amplió para permitir cualquier import cuyo
paquete raíz ya esté inyectado de confianza en el sandbox (`time`, `collections`, `numpy`,
`pandas`, `duckdb`) — `os`/`subprocess`/`sys`/`io` siguen bloqueados igual que antes.

---

## Cómo agregar un conector nuevo (ejemplo: MySQL)

Agregar un origen de datos nuevo no requiere tocar ningún archivo existente del patrón —
solo crear un archivo nuevo y sumar dos líneas de integración.

### Paso 1: elegir la base (DataFrame vs. SQL nativo)

MySQL tiene motor SQL propio, así que hereda de `SqlNativeConnector` (igual que Postgres), no
de `DataFrameBackedConnector`. DuckDB tiene una extensión `mysql` con soporte de `ATTACH`
análogo al de `postgres` — conviene revisar la documentación de esa extensión para confirmar la
sintaxis exacta del DSN y qué opciones soporta (ej. si `READ_ONLY` está disponible igual que en
`postgres`).

### Paso 2: crear `sheets_reports/connectors/mysql.py`

```python
import duckdb
import pydantic

from sheets_reports.connectors.base import (
    DataSourceConnectionError,
    SqlNativeConnector,
    TableInfo,
)
from sheets_reports.connectors.registry import connector


class MySQLConfig(pydantic.BaseModel):
    host: str
    port: int = 3306
    database: str
    user: str
    password: str


@connector("mysql")
class MySQLConnector(SqlNativeConnector):

    def __init__(self, config: dict):
        super().__init__(config)
        self._cfg = MySQLConfig(**config)

    @classmethod
    def config_schema(cls) -> type[pydantic.BaseModel]:
        return MySQLConfig

    def extension_name(self) -> str:
        return "mysql"

    def attach_clause(self, alias: str) -> str:
        c = self._cfg
        dsn = f"host={c.host} port={c.port} database={c.database} user={c.user} password={c.password}"
        dsn_sql_literal = dsn.replace("'", "''")
        return f"ATTACH '{dsn_sql_literal}' AS {alias} (TYPE mysql, READ_ONLY)"

    def _connect_and_attach(self, alias: str = "mysql") -> duckdb.DuckDBPyConnection:
        con = duckdb.connect(":memory:")
        try:
            self.register(con, alias)
        except Exception:
            con.close()
            raise
        return con

    def test_connection(self) -> None:
        try:
            con = self._connect_and_attach()
        except Exception as e:
            raise DataSourceConnectionError(str(e)) from e
        con.close()

    def list_tables(self) -> list[TableInfo]:
        # Igual que PostgresConnector.list_tables(): ATTACH, consultar information_schema.columns
        # del catálogo adjuntado, agrupar por tabla, traer unas pocas filas de ejemplo por tabla.
        ...
```

No hace falta reescribir esta clase desde cero: `sheets_reports/connectors/postgres.py` es la
referencia más cercana — el código de `list_tables()` es casi calcable, solo cambia el nombre
del catálogo de sistema si MySQL lo expone distinto a `information_schema` en DuckDB (hay que
verificarlo contra la extensión real).

### Paso 3: registrarlo en `ensure_loaded()`

En `sheets_reports/connectors/registry.py`:

```python
def ensure_loaded() -> None:
    import sheets_reports.connectors.google_sheets  # noqa: F401
    import sheets_reports.connectors.postgres  # noqa: F401
    import sheets_reports.connectors.mysql  # noqa: F401  <- agregar esta línea
```

### Paso 4: sumar el tipo al modelo

En `sheets_reports/models.py`, agregar el choice a `DataSource.SourceType`:

```python
class SourceType(models.TextChoices):
    GOOGLE_SHEETS = "google_sheets", "Google Sheets"
    POSTGRES = "postgres", "PostgreSQL"
    MYSQL = "mysql", "MySQL"          # <- nuevo
```

Correr `python manage.py makemigrations sheets_reports` para generar la migración del `choices`
nuevo (no cambia el esquema real, solo la validación del campo).

### Paso 5 (opcional): prompt de IA específico

Si querés que los widgets de dashboards MySQL usen SQL igual que Postgres, en
`sheets_reports/utils/generate_widget_ia.py` sumar la entrada al mapa:

```python
SYSTEM_INSTRUCTION_BY_SOURCE_TYPE = {
    "google_sheets": SYSTEM_INSTRUCTION_TEMPLATE,
    "postgres": SYSTEM_INSTRUCTION_TEMPLATE_POSTGRES,
    "mysql": SYSTEM_INSTRUCTION_TEMPLATE_POSTGRES,   # o un template propio si hace falta
}
```

Como el prompt de Postgres ya es genérico sobre `get_query_connection` + SQL (no menciona nada
específico de Postgres salvo el nombre del catálogo `postgres.*`), probablemente sirva con
mínimos ajustes de texto, o incluso tal cual si no importa que diga "Postgres" en vez de
"MySQL" en la explicación.

### Paso 6: dar de alta una conexión y probarla

Hoy no hay UI para crear un `DataSource` que no sea Sheets — se hace vía Django admin
(`/admin/sheets_reports/datasource/`), completando `source_type=mysql` y el `config` JSON
(`host`, `port`, `database`, `user`, `password`). Para probarla sin pasar por la UI:

```python
from sheets_reports.models import DataSource
ds = DataSource.objects.get(source_type="mysql")
ds.get_connector().test_connection()
ds.get_connector().list_tables()
```

Y para verificar el registro en DuckDB de punta a punta:

```python
from sheets_reports.utils.duckdb_query import get_query_connection
con = get_query_connection(dashboard)  # dashboard.data_source apuntando al MySQL
print(con.execute("SHOW ALL TABLES").fetchall())
```

Eso es todo lo que hace falta — ningún otro archivo del patrón (`base.py`, `cache.py`,
`duckdb_query.py`, `views_dashboard.py`) necesita cambios para soportar un tipo de origen
nuevo.
