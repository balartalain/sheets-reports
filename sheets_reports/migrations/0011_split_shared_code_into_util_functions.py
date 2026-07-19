import ast

from django.db import migrations


def _split_functions(source: str):
    """Parsea `source` y retorna una lista de (name, signature, description, source_code) por
    cada función de nivel superior. Si el parseo falla, retorna una lista vacía (el caller usa
    un fallback que preserva el texto completo igual)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    functions = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args_src = ast.unparse(node.args)
        signature = f"({args_src})"
        if node.returns is not None:
            signature += f" -> {ast.unparse(node.returns)}"
        description = ast.get_docstring(node) or ""
        source_code = ast.get_source_segment(source, node) or ""
        functions.append((node.name, signature, description, source_code))
    return functions


def split_shared_code(apps, schema_editor):
    Dashboard = apps.get_model("sheets_reports", "Dashboard")
    DashboardUtilFunction = apps.get_model("sheets_reports", "DashboardUtilFunction")

    for dashboard in Dashboard.objects.exclude(shared_code=""):
        functions = _split_functions(dashboard.shared_code)
        if not functions:
            functions = [("legacy_shared_code", "()", "", dashboard.shared_code)]

        used_names = set()
        for name, signature, description, source_code in functions:
            final_name = name
            i = 2
            while final_name in used_names:
                final_name = f"{name}_{i}"
                i += 1
            used_names.add(final_name)

            DashboardUtilFunction.objects.create(
                dashboard=dashboard,
                name=final_name,
                signature=signature,
                description=description,
                category="Personalizada",
                source_code=source_code,
                created_from_prompt=dashboard.shared_code_prompt or "",
            )


class Migration(migrations.Migration):

    dependencies = [
        ("sheets_reports", "0010_dashboardutilfunction"),
    ]

    operations = [
        migrations.RunPython(split_shared_code, migrations.RunPython.noop),
    ]
