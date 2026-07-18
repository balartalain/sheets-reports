document.addEventListener('alpine:init', () => {
  Alpine.store('dashboard', {
    widgets: [],
    editingId: null,
    editingType: null,
    dashboardId: window.DASHBOARD_ID,
    availableFunctions: [],
    drawerDraft: {},
    drawerGenerating: false,
    drawerGenerateError: '',
    sharedCodeOpen: false,
    sharedCodeDraft: { prompt: '', code: '' },
    sharedCodeGenerating: false,
    sharedCodeGenerateError: '',
    _nextId: -1,

    get flatFunctions() {
      return this.availableFunctions.map(name => ({ path: name, label: name }));
    },

    async refreshAvailableFunctions() {
      try {
        const r = await fetch(`/api/widget-functions/${window.DASHBOARD_SLUG}/`);
        this.availableFunctions = await r.json();
      } catch (e) {}
    },

    async loadSharedCode() {
      try {
        const r = await fetch(`/api/dashboard/${this.dashboardId}/shared-code/`);
        const data = await r.json();
        this.sharedCodeDraft = { prompt: data.shared_code_prompt || '', code: data.shared_code || '' };
      } catch (e) {}
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
          prompt: w.prompt || '',
          code: w.code || '',
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
      this.drawerGenerateError = '';
    },

    async generateWidgetCode() {
      if (!this.drawerDraft.prompt) return;
      this.drawerGenerating = true;
      this.drawerGenerateError = '';
      try {
        const r = await fetch(`/api/dashboard/${this.dashboardId}/generate-widget-code/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt: this.drawerDraft.prompt,
            widget_id: this.editingId > 0 ? this.editingId : null,
            chart_type: this.editingType,
            existing_code: this.drawerDraft.code,
          }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || 'Error generando código');
        this.drawerDraft.code = data.code;
      } catch (e) {
        this.drawerGenerateError = e.message;
      } finally {
        this.drawerGenerating = false;
      }
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

    openSharedCodePanel() {
      this.sharedCodeOpen = true;
    },

    closeSharedCodePanel() {
      this.sharedCodeOpen = false;
      this.sharedCodeGenerateError = '';
    },

    async generateSharedCode() {
      if (!this.sharedCodeDraft.prompt) return;
      this.sharedCodeGenerating = true;
      this.sharedCodeGenerateError = '';
      try {
        const r = await fetch(`/api/dashboard/${this.dashboardId}/generate-shared-code/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt: this.sharedCodeDraft.prompt,
            existing_code: this.sharedCodeDraft.code,
          }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || 'Error generando código');
        this.sharedCodeDraft.code = data.code;
      } catch (e) {
        this.sharedCodeGenerateError = e.message;
      } finally {
        this.sharedCodeGenerating = false;
      }
    },

    async saveSharedCode() {
      try {
        await fetch(`/api/dashboard/${this.dashboardId}/shared-code/`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            shared_code: this.sharedCodeDraft.code,
            shared_code_prompt: this.sharedCodeDraft.prompt,
          }),
        });
      } catch (e) {}
      this.closeSharedCodePanel();
    },
  });
});
