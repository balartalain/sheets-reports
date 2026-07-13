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
