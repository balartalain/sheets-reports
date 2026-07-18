import logging
from pathlib import Path

from django.db import models
from django.conf import settings
from django.utils.text import slugify

logger = logging.getLogger(__name__)

SERVER_FUNCTIONS_DIR = Path(__file__).resolve().parent / "server_functions"


class Dashboard(models.Model):
    """Tablero de reportes que agrupa widgets visuales."""
    source_url = models.URLField(
        max_length=500,
        help_text="URL de la hoja de Google Sheets de donde se extraerán los datos.",
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
    functions_slug = models.SlugField(
        max_length=255,
        unique=True,
        blank=True,
        null=True,
        help_text="Identificador interno y permanente usado para ubicar server_functions/<functions_slug>/. Se genera una sola vez al crear el tablero y nunca cambia, aunque se edite el título.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboards",
        help_text="Usuario propietario del tablero.",
    )
    shared_code = models.TextField(
        blank=True,
        default="",
        help_text="Código Python compartido por todos los widgets del tablero (funciones reutilizables, ej. columnas calculadas). Se inyecta en el exec() de cada widget antes de su propio código.",
    )
    shared_code_prompt = models.TextField(
        blank=True,
        default="",
        help_text="Último prompt usado para generar shared_code vía IA.",
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
        if not self.functions_slug:
            self.functions_slug = self._generate_unique_slug("functions_slug")
            self._scaffold_server_functions_folder()
        if not self.slug or self.title != self._original_title:
            self.slug = self._generate_unique_slug("slug")
        super().save(*args, **kwargs)
        self._original_title = self.title

    def _scaffold_server_functions_folder(self):
        """Crea server_functions/<functions_slug>/functions.py una sola vez, al crear el tablero."""
        functions_file = SERVER_FUNCTIONS_DIR / self.functions_slug / "functions.py"
        if functions_file.exists():
            return
        try:
            functions_file.parent.mkdir(parents=True, exist_ok=True)
            functions_file.write_text(
                f'"""\n'
                f'Vistas de datos para el tablero "{self.title}" (functions_slug: {self.functions_slug}).\n'
                f'Cada función recibe (request, widget) y retorna un JsonResponse. Cada una es\n'
                f'responsable de cargar su(s) propio(s) DataFrame con\n'
                f'`get_cached_df(widget.dashboard, sheet_name)` (sheet_name=None usa la primera\n'
                f'hoja), lo que permite cruzar datos de varias pestañas del mismo spreadsheet\n'
                f'cuando haga falta.\n'
                f'"""\n'
            )
        except OSError:
            logger.warning(
                "No se pudo crear server_functions/%s/functions.py automáticamente",
                self.functions_slug, exc_info=True,
            )


class WidgetInstance(models.Model):
    """Widget individual dentro de un tablero (gráfico, KPI, filtro, etc.)."""
    CHART_TYPES = [
        ("bar", "Gráfico de Barras"),
        ("line", "Gráfico de Líneas"),
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
    function_path = models.CharField(
        max_length=255,
        default="",
        help_text="Nombre de la función del servidor definida en server_functions/<slug del tablero>/functions.py (ej. 'total_ventas'). Se usa solo si `code` está vacío.",
    )
    code = models.TextField(
        blank=True,
        default="",
        help_text="Código Python ejecutado por el widget (debe definir `def run(request, widget):` que retorna un JsonResponse). Si está vacío, se usa function_path.",
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
        """Nombre exacto de columna a filtrar (solo widgets chart_type='filter'), configurado
        por el usuario en el drawer y guardado en properties.filterField."""
        return (self.properties or {}).get("filterField", "")
