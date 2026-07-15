function renderPalette(sidebarEl) {
  sidebarEl.innerHTML = WidgetRegistry.getPaletteEntries().map(entry => `
    <div class="flex items-center p-3.5 ${entry.chipClass} rounded-xl cursor-grab transition active:cursor-grabbing"
         data-type="${entry.type}" style="--ghost-span: ${entry.ghostSpan};">
      <div class="mr-3 text-xl">${entry.icon}</div>
      <div>
        <span class="block text-sm font-semibold ${entry.titleClass}">${entry.label}</span>
        <span class="block text-[11px] ${entry.descClass}">${entry.description}</span>
      </div>
    </div>
  `).join('');
}

document.addEventListener('DOMContentLoaded', async () => {
  const canvasEl = document.getElementById('dashboard-canvas');
  const sidebarEl = document.getElementById('sidebar-components');
  const store = Alpine.store('dashboard');

  renderPalette(sidebarEl);

  await store.loadWidgetsFromServer();
  store.widgets.forEach(w => {
    canvasEl.appendChild(w.mount());
  });
  store.widgets.forEach(w => w.fetchAndRender());

  fetch('/api/widget-functions/')
    .then(r => r.json())
    .then(data => { store.availableFunctions = data; })
    .catch(() => {});

  requestAnimationFrame(() => {
    window.dispatchEvent(new Event('resize'));
  });

  new Sortable(sidebarEl, {
    group: { name: 'shared', pull: 'clone', put: false },
    sort: false,
    animation: 150,
  });

  new Sortable(canvasEl, {
    group: 'shared',
    animation: 150,
    ghostClass: 'grid-ghost-preview',
    handle: '.drag-handle',

    onAdd: function (evt) {
      const type = evt.item.getAttribute('data-type');
      const widget = store.addWidget(type);
      const widgetEl = widget.mount();
      evt.item.replaceWith(widgetEl);
      requestAnimationFrame(() => {
        window.dispatchEvent(new Event('resize'));
      });
    },

    onEnd: function () {
      store.reorderWidgets();
    },
  });

  document.getElementById('save-btn').addEventListener('click', async () => {
    const store = Alpine.store('dashboard');
    store.reorderWidgets();
    for (const w of store.widgets) {
      if (w._dirty) await store._saveWidget(w);
    }
    alert('Widgets guardados en la base de datos.');
  });

  document.getElementById('share-btn').addEventListener('click', () => {
    const url = `${window.location.origin}/tableros/${window.DASHBOARD_SLUG}/shared/`;
    window.prompt('Enlace para compartir (solo lectura):', url);
  });
});
