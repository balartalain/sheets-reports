"""
Registro de tipos de conector disponibles (DataSource.source_type -> clase DataConnector),
mismo idioma que sheets_reports.utils.registry (@util -> UTILS_REGISTRY): un decorador
llena un dict a nivel de módulo, y ensure_loaded() fuerza el import de los módulos que
definen conectores (import diferido para no ciclar, ya que esos módulos importan
`connector` desde este mismo archivo). Agregar un tipo nuevo (ej. MySQL) es: un archivo
nuevo con su clase decorada con @connector("mysql"), y una línea en ensure_loaded() -- nada
más necesita cambiar.
"""
from sheets_reports.connectors.base import DataConnector

CONNECTOR_REGISTRY: dict[str, type[DataConnector]] = {}


def connector(kind: str):
    """Decorador que registra una clase DataConnector bajo el discriminador `kind`
    (debe coincidir con DataSource.SourceType)."""
    def decorator(cls: type[DataConnector]) -> type[DataConnector]:
        CONNECTOR_REGISTRY[kind] = cls
        return cls
    return decorator


def ensure_loaded() -> None:
    import sheets_reports.connectors.google_sheets  # noqa: F401 (registra "google_sheets")
    import sheets_reports.connectors.postgres  # noqa: F401 (registra "postgres")


def get_connector_class(kind: str) -> type[DataConnector]:
    ensure_loaded()
    try:
        return CONNECTOR_REGISTRY[kind]
    except KeyError:
        raise ValueError(f"Tipo de origen de datos desconocido: {kind!r}") from None


def get_connector(data_source) -> DataConnector:
    """`data_source` es una instancia de sheets_reports.models.DataSource."""
    cls = get_connector_class(data_source.source_type)
    return cls(data_source.config)
