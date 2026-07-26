from django.db import models
from django.conf import settings
from django.utils.text import slugify


class DataSource(models.Model):
    """
    Origen de datos configurado (Google Sheets, Postgres, ...), desacoplado del Dashboard que
    lo usa para poder reutilizarse entre varios tableros. El tipo (source_type) determina qué
    DataConnector (ver sheets_reports.connectors) interpreta `config`: para "google_sheets" es
    {"source_url": "..."}; para "postgres", host/port/database/user/password/sslmode. La forma
    exacta de cada tipo la valida el pydantic BaseModel que devuelve
    connectors.<tipo>.config_schema(), no este modelo.
    """
    class SourceType(models.TextChoices):
        GOOGLE_SHEETS = "google_sheets", "Google Sheets"
        POSTGRES = "postgres", "PostgreSQL"

    name = models.CharField(
        max_length=255,
        help_text="Nombre descriptivo de esta conexión (ej. 'Ventas - Postgres prod').",
    )
    source_type = models.CharField(
        max_length=30,
        choices=SourceType.choices,
        help_text="Tipo de origen de datos; determina qué conector (sheets_reports.connectors) lo interpreta.",
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuración específica del tipo de origen (URL de sheet, credenciales de Postgres, etc.).",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="data_sources",
        help_text="Usuario propietario de esta conexión.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Origen de Datos"
        verbose_name_plural = "Orígenes de Datos"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_source_type_display()})"

    def get_connector(self):
        from sheets_reports.connectors.registry import get_connector
        return get_connector(self)


class Dashboard(models.Model):
    """Tablero de reportes que agrupa widgets visuales."""
    source_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text=(
            "OBSOLETO: URL de Google Sheets, reemplazado por `data_source`. Se conserva "
            "temporalmente solo para el fallback de lectura durante la migración a DataSource."
        ),
    )
    data_source = models.ForeignKey(
        DataSource,
        on_delete=models.PROTECT,
        related_name="dashboards",
        null=True,
        blank=True,
        help_text="Origen de datos de este tablero.",
    )
    title = models.CharField(
        max_length=255,
        help_text="Título descriptivo del tablero.",
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        blank=True,
        null=True,
        help_text="Identificador único usado en la URL del tablero, generado a partir del título. Se actualiza cada vez que cambia el título.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboards",
        help_text="Usuario propietario del tablero.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Fecha y hora de creación del tablero.",
    )

    class Meta:
        verbose_name = "Dashboard"
        verbose_name_plural = "Dashboards"
        ordering = ["-created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_title = self.title

    def __str__(self):
        return self.title

    def _generate_unique_slug(self, field_name):
        base_slug = slugify(self.title) or "tablero"
        slug = base_slug
        i = 2
        while Dashboard.objects.exclude(pk=self.pk).filter(**{field_name: slug}).exists():
            slug = f"{base_slug}-{i}"
            i += 1
        return slug

    def save(self, *args, **kwargs):
        if not self.slug or self.title != self._original_title:
            self.slug = self._generate_unique_slug("slug")
        super().save(*args, **kwargs)
        self._original_title = self.title


class WidgetInstance(models.Model):
    """Widget individual dentro de un tablero (gráfico, KPI, filtro, etc.)."""
    CHART_TYPES = [
        ("bar", "Gráfico de Barras"),
        ("line", "Gráfico de Líneas"),
        ("donut", "Gráfico de Dona"),
        ("kpi", "Tarjeta KPI"),
        ("filter", "Filtro"),
        ("table", "Tabla"),
    ]

    dashboard = models.ForeignKey(
        Dashboard,
        on_delete=models.CASCADE,
        related_name="widgets",
        help_text="Tablero al que pertenece este widget.",
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Título opcional que se muestra en la cabecera del widget.",
    )
    chart_type = models.CharField(
        max_length=20,
        choices=CHART_TYPES,
        help_text="Tipo de gráfico o componente visual.",
    )
    code = models.TextField(
        blank=True,
        default="",
        help_text="Código Python ejecutado por el widget (debe definir `def run(request, widget):` que retorna un JsonResponse).",
    )
    prompt = models.TextField(
        blank=True,
        default="",
        help_text="Último prompt en lenguaje natural usado para generar `code` vía IA.",
    )
    properties = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON con todas las propiedades del frontend necesarias para renderizar el widget (ancho, alto, colores, etc.).",
    )
    order = models.IntegerField(
        default=0,
        help_text="Orden del widget en el lienzo (posición).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Fecha y hora de creación del widget.",
    )

    class Meta:
        verbose_name = "Widget Instance"
        verbose_name_plural = "Widget Instances"
        ordering = ["order", "created_at"]

    def __str__(self):
        return self.title or f"{self.get_chart_type_display()} ({self.id})"

    @property
    def filter_field(self):
        """Nombre exacto de columna a filtrar (solo widgets chart_type='filter'), detectado
        automáticamente a partir de la clave "field" que devuelve el código del widget al
        ejecutarse, y guardado en properties.filterField (ver widget_dispatcher._sync_filter_field)."""
        return (self.properties or {}).get("filterField", "")

    @filter_field.setter
    def filter_field(self, value):
        self.properties = {**(self.properties or {}), "filterField": value or ""}


class DashboardUtilFunction(models.Model):
    """Función utilitaria personalizada de un tablero (ej. una columna calculada), generada
    vía IA o editada a mano. Se inyecta en el exec() de cada widget de ese tablero, junto con
    las utilidades del sistema (ver sheets_reports.utils.registry)."""
    dashboard = models.ForeignKey(Dashboard, related_name='custom_utils', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    signature = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=50, default='Personalizada')
    source_code = models.TextField()
    created_from_prompt = models.TextField(blank=True)  # qué pidió el usuario para generarla
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Función Utilitaria del Tablero"
        verbose_name_plural = "Funciones Utilitarias del Tablero"
        unique_together = [('dashboard', 'name')]
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} ({self.dashboard.title})"
