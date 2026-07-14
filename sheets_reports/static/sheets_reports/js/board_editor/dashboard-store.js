document.addEventListener('alpine:init', () => {
  Alpine.store('dashboard', {
    widgets: [],
    editingId: null,
    editingType: null,
    dashboardId: window.DASHBOARD_ID,
    availableFunctions: [],
    drawerDraft: {},
    _nextId: -1,

    get flatFunctions() {
      const result = [];
      for (const group of this.availableFunctions) {
        for (const fn of group.functions) {
          result.push({ ...fn, label: group.module + ' / ' + fn.name });
        }
      }
      return result;
    },

    async loadWidgetsFromServer() {
      try {
        const r = await fetch(`/api/dashboard/${this.dashboardId}/widgets/`);
        const data = await r.json();
        data.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
        this.widgets = data.map(w => WidgetRegistry.create(w.chart_type, {
          id: w.id,
          title: w.title,
          functionPath: w.function_path || '',
          order: w.order ?? 0,
          ...(w.properties || {}),
        }));
      } catch (e) {
        this.widgets = [];
      }
    },

    addWidget(type) {
      const widget = WidgetRegistry.create(type, {
        id: this._nextId--,
        order: this.widgets.length,
        _dirty: true,
      });
      this.widgets.push(widget);
      return widget;
    },

    async _saveWidget(w) {
      const body = w.toPayload();
      if (w.id > 0) {
        await fetch(`/api/widget/${w.id}/`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
      } else {
        const r = await fetch(`/api/dashboard/${this.dashboardId}/widgets/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await r.json();
        const oldId = w.id;
        w.id = data.id;
        if (w.el) {
          w.el.dataset.widgetId = data.id;
          const chartContainer = w.el.querySelector(`#chart-${oldId}`);
          if (chartContainer) chartContainer.id = `chart-${data.id}`;
        }
      }
      w._dirty = false;
    },

    async removeWidget(id) {
      if (id > 0) {
        try { await fetch(`/api/widget/${id}/`, { method: 'DELETE' }); } catch (e) {}
      }
      this.widgets = this.widgets.filter(w => w.id !== id);
    },

    reorderWidgets() {
      const canvasEl = document.getElementById('dashboard-canvas');
      if (!canvasEl) return;
      const widgetEls = canvasEl.querySelectorAll('[data-widget-id]');
      widgetEls.forEach((el, i) => {
        const id = parseInt(el.dataset.widgetId);
        const w = this.widgets.find(w => w.id === id);
        if (w && w.order !== i) {
          w.order = i;
          w._dirty = true;
        }
      });
      this.widgets.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    },

    get drawerFields() {
      // No debe colapsar a []: eso destruiría/recrearía el <select> de
      // functionPath (y sus <option>) en cada apertura del drawer.
      const WidgetClass = this.editingType ? WidgetRegistry.get(this.editingType) : BaseWidget;
      return WidgetClass.drawerFields;
    },

    openDrawer(id) {
      const w = this.widgets.find(w => w.id === id);
      if (!w) return;
      this.editingId = id;
      this.editingType = w.chart_type;
      const draft = {};
      for (const field of this.drawerFields) draft[field.key] = w[field.key];
      this.drawerDraft = draft;
    },

    closeDrawer() {
      this.editingId = null;
      this.editingType = null;
      this.drawerDraft = {};
    },

    async saveDrawer() {
      const w = this.widgets.find(w => w.id === this.editingId);
      if (!w) return;
      Object.assign(w, this.drawerDraft);
      w._dirty = true;

      await this._saveWidget(w);
      w.updateChrome();
      this.closeDrawer();
      w.fetchAndRender();
    },

    fetchWidgetData(w) {
      return w.fetchAndRender();
    },
  });
});
