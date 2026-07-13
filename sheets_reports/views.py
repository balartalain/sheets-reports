import importlib
import inspect
from pathlib import Path

from django.http import JsonResponse
from django.shortcuts import render

from sheets_reports.utils.widget_dispatcher import dispatch_widget


def home(request):
    return render(request, 'home.html')


def board_editor(request, board_id):
    return render(request, 'board_editor.html')


def widget_data(request, widget_id):
    """
    Endpoint AJAX que retorna los datos procesados para un widget específico.
    Delega en el dispatcher que importa el módulo de vistas del tablero
    y ejecuta la función correspondiente.
    """
    return dispatch_widget(request, widget_id)


def widget_functions(request):
    """
    Escanea sheets_reports/views_*.py y retorna las funciones disponibles
    agrupadas por módulo. Solo incluye funciones definidas por el usuario
    (no las importadas ni las privadas que empiezan con _).
    """
    views_dir = Path(__file__).parent
    modules = []

    for filepath in sorted(views_dir.glob("views_*.py")):
        module_name = f"sheets_reports.{filepath.stem}"
        module = importlib.import_module(module_name)

        functions = []
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_"):
                continue
            # Solo funciones definidas en este módulo, no importadas
            if getattr(obj, "__module__", None) == module_name:
                functions.append({
                    "path": f"{filepath.stem}.{name}",
                    "name": name,
                })

        if functions:
            modules.append({
                "module": filepath.stem.replace("views_", ""),
                "functions": functions,
            })

    return JsonResponse(modules, safe=False)
