import json
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.utils.timesince import timesince
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from sheets_reports.models import Dashboard


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
