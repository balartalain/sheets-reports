from django.db import models
from django.conf import settings
from django.utils.text import slugify


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
        help_text="Identificador único usado en la URL del tablero, generado a partir del título.",
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

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "tablero"
            slug = base_slug
            i = 2
            while Dashboard.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base_slug}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)


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
        help_text="Nombre de la función del servidor definida en server_functions/<slug del tablero>/functions.py (ej. 'total_ventas').",
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
