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

function showToast(message) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'fixed top-6 left-1/2 -translate-x-1/2 z-[100] flex flex-col items-center gap-2';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = 'bg-ink text-white text-sm font-medium px-4 py-2.5 rounded-xl shadow-lg opacity-0 transition-opacity duration-200';
  toast.textContent = message;
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.remove('opacity-0');
  });

  setTimeout(() => {
    toast.classList.add('opacity-0');
    setTimeout(() => toast.remove(), 200);
  }, 2000);
}

async function copyToClipboard(text) {
  if (navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (err) {
      // fall through to legacy fallback below
    }
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
}

function setupHeaderAutoHide() {
  const HIDE_THRESHOLD = 20;
  const mainEl = document.getElementById('board-main');
  const headerEl = document.getElementById('app-header');
  const bodyEl = document.getElementById('board-body');
  if (!mainEl || !headerEl || !bodyEl) return;

  let headerHidden = false;
  mainEl.addEventListener('scroll', () => {
    const shouldHide = mainEl.scrollTop > HIDE_THRESHOLD;
    if (shouldHide === headerHidden) return;
    headerHidden = shouldHide;
    headerEl.classList.toggle('header-hidden', headerHidden);
    bodyEl.classList.toggle('header-hidden', headerHidden);
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  const canvasEl = document.getElementById('dashboard-canvas');
  const sidebarEl = document.getElementById('sidebar-components');
  const store = Alpine.store('dashboard');

  setupHeaderAutoHide();
  renderPalette(sidebarEl);

  await store.loadWidgetsFromServer();
  store.widgets.forEach(w => {
    canvasEl.appendChild(w.mount());
  });
  store.widgets.forEach(w => w.observeForLazyLoad());

  store.loadUtils();

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
      widget.observeForLazyLoad();
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

  document.getElementById('share-btn').addEventListener('click', async () => {
    const base = `${window.location.origin}${window.SHARE_PATH}`;
    const qs = Alpine.store('dashboard').getFilterQueryString
      ? Alpine.store('dashboard').getFilterQueryString()
      : '';
    const url = qs ? base + '?' + qs : base;
    await copyToClipboard(url);
    showToast('Enlace copiado');
  });
});
