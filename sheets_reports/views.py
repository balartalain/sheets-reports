from django.shortcuts import render

def home(request):
    return render(request, 'home.html')

def board_editor(request, board_id):
    return render(request, 'board_editor.html')
