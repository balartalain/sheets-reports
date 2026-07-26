import json
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.http import JsonResponse, StreamingHttpResponse
from django.utils.timesince import timesince
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from sheets_reports.models import Dashboard, DataSource
from sheets_reports.utils.generate_dashboard_ia import generate_board_from_prompt


def _get_user(request):
    if request.user.is_authenticated:
        return request.user
    user = get_user_model().objects.filter(is_superuser=True).first()
    if not user:
        user = get_user_model().objects.first()
    return user


def _sheet_name(source_url):
    if not source_url:
        return ""
    import re
    m = re.search(r'/spreadsheets/d/([^/]+)', source_url)
    if m:
        return m.group(1)
    try:
        path = urlparse(source_url).path
        return path.strip("/").split("/")[-1] or path.strip("/")
    except Exception:
        return source_url


def _serialize(dashboard):
    data_source = dashboard.data_source
    source_url = ""
    if data_source and data_source.source_type == DataSource.SourceType.GOOGLE_SHEETS:
        source_url = data_source.config.get("source_url", "")
    return {
        "id": dashboard.id,
        "title": dashboard.title,
        "slug": dashboard.slug,
        "source_url": source_url,
        "sheetName": _sheet_name(source_url),
        "data_source": {
            "id": data_source.id,
            "name": data_source.name,
            "source_type": data_source.source_type,
        } if data_source else None,
        "cardCount": dashboard.widgets.count(),
        "created_at": dashboard.created_at.isoformat(),
        "updated": timesince(dashboard.created_at, now()),
    }


def _resolve_data_source(data, user, name_hint):
    """
    Resuelve la DataSource a partir del payload de un request de creación/generación de
    dashboard: si trae `data_source_id`, reutiliza una DataSource ya existente (el único
    camino hoy para usar un origen no-Sheets, ej. Postgres, dado que todavía no hay UI para
    crearlos -- se dan de alta vía Django admin). Si trae `source_url`, crea una DataSource
    "google_sheets" nueva sobre la marcha, por compatibilidad con el formulario actual (que
    solo conoce source_url). Retorna (data_source, None) o (None, JsonResponse de error).
    """
    data_source_id = data.get("data_source_id")
    if data_source_id:
        try:
            return DataSource.objects.get(id=data_source_id), None
        except DataSource.DoesNotExist:
            return None, JsonResponse({"error": "Origen de datos no encontrado"}, status=404)

    source_url = (data.get("source_url") or "").strip()
    if source_url:
        data_source = DataSource.objects.create(
            name=f"{name_hint} (Sheets)",
            source_type=DataSource.SourceType.GOOGLE_SHEETS,
            config={"source_url": source_url},
            owner=user,
        )
        return data_source, None

    return None, JsonResponse({"error": "Se requiere data_source_id o source_url"}, status=400)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def dashboard_list(request):
    if request.method == "GET":
        dashboards = Dashboard.objects.all().order_by("-created_at")
        return JsonResponse([_serialize(d) for d in dashboards], safe=False)

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)

    title = data.get("title", "").strip()
    if not title:
        return JsonResponse({"error": "El título es obligatorio"}, status=400)

    user = _get_user(request)
    if not user:
        return JsonResponse({"error": "No hay usuario disponible"}, status=401)

    data_source, error = _resolve_data_source(data, user, title)
    if error:
        return error

    dashboard = Dashboard.objects.create(
        title=title,
        data_source=data_source,
        user=user,
    )
    return JsonResponse(_serialize(dashboard), status=201)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def dashboard_detail(request, dashboard_id):
    try:
        dashboard = Dashboard.objects.get(id=dashboard_id)
    except Dashboard.DoesNotExist:
        return JsonResponse({"error": "Dashboard no encontrado"}, status=404)

    if request.method == "DELETE":
        dashboard.delete()
        return JsonResponse({"deleted": True})

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)

    if "title" in data:
        title = data["title"].strip()
        if not title:
            return JsonResponse({"error": "El título no puede estar vacío"}, status=400)
        dashboard.title = title
    if "data_source_id" in data:
        try:
            dashboard.data_source = DataSource.objects.get(id=data["data_source_id"])
        except DataSource.DoesNotExist:
            return JsonResponse({"error": "Origen de datos no encontrado"}, status=404)
    elif "source_url" in data:
        source_url = (data["source_url"] or "").strip()
        if dashboard.data_source_id and dashboard.data_source.source_type == DataSource.SourceType.GOOGLE_SHEETS:
            dashboard.data_source.config = {"source_url": source_url}
            dashboard.data_source.save(update_fields=["config", "updated_at"])
        else:
            dashboard.data_source = DataSource.objects.create(
                name=f"{dashboard.title} (Sheets)",
                source_type=DataSource.SourceType.GOOGLE_SHEETS,
                config={"source_url": source_url},
                owner=dashboard.user,
            )
    dashboard.save()
    return JsonResponse(_serialize(dashboard))


def _get_request_data(request):
    """Extrae datos del request sin importar el método HTTP o content-type."""
    if request.content_type and "application/json" in request.content_type:
        return json.loads(request.body)
    if request.method == "POST":
        return request.POST
    if request.method == "PUT":
        try:
            return json.loads(request.body) if request.body else {}
        except (json.JSONDecodeError, AttributeError):
            return {}
    return request.GET


def _sse_event(event: dict) -> str:
    """Formatea un dict de progreso como un evento Server-Sent Events (una línea `event:`
    con el tipo, una línea `data:` con el resto como JSON, línea en blanco de separador)."""
    event = dict(event)
    event_type = event.pop("event")
    return f"event: {event_type}\ndata: {json.dumps(event)}\n\n"


@csrf_exempt
@require_http_methods(["POST"])
def generate_dashboard_from_prompt(request):
    """
    POST /api/dashboards/generate-from-prompt/
    Crea un tablero completo desde una descripción en lenguaje natural, transmitiendo el
    progreso en vivo como Server-Sent Events (text/event-stream) mientras Gemini arma el plan
    y genera el código de cada widget — esto puede tardar bastante con varios widgets, así que
    el cliente ve avance real en vez de esperar a ciegas.
    Body: { "prompt": "...", "source_url": "..." } o { "prompt": "...", "data_source_id": N }
    (data_source_id apunta a una DataSource ya creada, ej. una conexión Postgres dada de alta
    vía Django admin; source_url crea una DataSource "google_sheets" nueva al vuelo, por
    compatibilidad con el formulario actual).
    Eventos emitidos (uno por línea `event: <tipo>` + `data: <json>`):
      planning                          -> arrancó el armado del plan del tablero
      plan       {title, total}         -> plan listo, se van a generar `total` widgets
      widget_start {index, total, title} -> arrancó la generación del widget `index`
      widget_done  {index, total, widget_id} -> terminó ese widget
      done       {dashboard: {...}}     -> tablero completo, mismo shape que POST /api/dashboards/
      error      {message}              -> algo falló; no queda ningún registro huérfano
    """
    try:
        data = _get_request_data(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)

    prompt = (data.get("prompt") or "").strip()

    if not prompt:
        return JsonResponse({"error": "El prompt es obligatorio"}, status=400)

    user = _get_user(request)
    if not user:
        return JsonResponse({"error": "No hay usuario disponible"}, status=401)

    data_source, error = _resolve_data_source(data, user, "Tablero generado")
    if error:
        return error

    def event_stream():
        try:
            for event in generate_board_from_prompt(prompt, data_source, user):
                if event["event"] == "done":
                    event = {"event": "done", "dashboard": _serialize(event["dashboard"])}
                yield _sse_event(event)
        except Exception as e:
            yield _sse_event({"event": "error", "message": str(e)})

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
