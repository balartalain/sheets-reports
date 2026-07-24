import json
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.http import JsonResponse, StreamingHttpResponse
from django.utils.timesince import timesince
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from sheets_reports.models import Dashboard
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
    return {
        "id": dashboard.id,
        "title": dashboard.title,
        "slug": dashboard.slug,
        "source_url": dashboard.source_url,
        "sheetName": _sheet_name(dashboard.source_url),
        "cardCount": dashboard.widgets.count(),
        "created_at": dashboard.created_at.isoformat(),
        "updated": timesince(dashboard.created_at, now()),
    }


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

    dashboard = Dashboard.objects.create(
        title=title,
        source_url=data.get("source_url", "").strip(),
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
    if "source_url" in data:
        dashboard.source_url = data["source_url"].strip()
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
    Body: { "prompt": "...", "source_url": "..." }
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
    source_url = (data.get("source_url") or "").strip()

    if not prompt:
        return JsonResponse({"error": "El prompt es obligatorio"}, status=400)
    if not source_url:
        return JsonResponse({"error": "La URL de la hoja es obligatoria"}, status=400)

    user = _get_user(request)
    if not user:
        return JsonResponse({"error": "No hay usuario disponible"}, status=401)

    def event_stream():
        try:
            for event in generate_board_from_prompt(prompt, source_url, user):
                if event["event"] == "done":
                    event = {"event": "done", "dashboard": _serialize(event["dashboard"])}
                yield _sse_event(event)
        except Exception as e:
            yield _sse_event({"event": "error", "message": str(e)})

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
