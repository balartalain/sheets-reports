document.addEventListener('alpine:init', () => {
  Alpine.store('dashboard', { dashboardId: window.DASHBOARD_ID });
});

document.addEventListener('DOMContentLoaded', async () => {
  const canvasEl = document.getElementById('dashboard-canvas');
  const r = await fetch(`/api/dashboard/${window.DASHBOARD_ID}/widgets/`);
  const data = await r.json();
  data.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

  const widgets = data.map(w => WidgetRegistry.create(w.chart_type, {
    id: w.id,
    title: w.title,
    functionPath: w.function_path || '',
    order: w.order ?? 0,
    ...(w.properties || {}),
  }));

  widgets.forEach(w => canvasEl.appendChild(w.mountReadOnly()));
  widgets.forEach(w => w.fetchAndRender());
});
