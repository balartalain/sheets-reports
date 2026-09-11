const AI_FETCH_TIMEOUT_MS = 60000;

// Como base-widget.js:fetchAndRender, pero para las llamadas de generación con IA del store:
// aborta si tarda demasiado y nunca truena por JSON inválido (p. ej. una página HTML de error
// devuelta por un timeout de gateway/proxy) — deja que quien llama decida el mensaje de error.
async function fetchJsonSafe(url, options = {}, timeoutMs = AI_FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const r = await fetch(url, { ...options, signal: controller.signal });
    const data = await r.json().catch(() => null);
    return { r, data };
  } finally {
    clearTimeout(timeoutId);
  }
}

document.addEventListener('alpine:init', () => {
  Alpine.store('dashboard', {
    widgets: [],
    editingId: null,
    editingType: null,
    dashboardId: window.DASHBOARD_ID,
    drawerDraft: {},
    drawerGenerating: false,
    drawerGenerateError: '',
    drawerUtilsOpen: false,
    drawerHelpOpen: false,
    utilsOpen: false,
    availableUtils: [],
    systemUtilsOpen: false,
    utilDraft: null,
    utilGenerating: false,
    utilGenerateError: '',
    calcColsOpen: false,
    calculatedColumns: [],
    availableTables: [],
    calcColDraft: null,
    calcColGenerating: false,
    calcColGenerateError: '',
    _nextId: -1,

    get calculatedColumnsByTable() {
      const byTable = {};
      for (const cc of this.calculatedColumns) {
        (byTable[cc.table_name] ??= []).push(cc);
      }
      return byTable;
    },

    get customUtils() {
      return this.availableUtils.filter(u => u.origin === 'custom');
    },

    get systemUtils() {
      return this.availableUtils.filter(u => u.origin === 'system');
    },

    async loadUtils() {
      try {
        const r = await fetch(apiUrl(`/api/dashboard/${this.dashboardId}/utils/`));
        this.availableUtils = await r.json();
      } catch (e) {}
    },

    async loadCalculatedColumns() {
      try {
        const r = await fetch(apiUrl(`/api/dashboard/${this.dashboardId}/calculated-columns/`));
        this.calculatedColumns = await r.json();
      } catch (e) {}
    },

    async loadAvailableTables() {
      try {
        const r = await fetch(apiUrl(`/api/dashboard/${this.dashboardId}/tables/`));
        this.availableTables = await r.json();
      } catch (e) {}
    },

    async loadWidgetsFromServer() {
      try {
        const r = await fetch(apiUrl(`/api/dashboard/${this.dashboardId}/widgets/`));
        const data = await r.json();
        data.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
        this.widgets = data.map(w => WidgetRegistry.create(w.chart_type, {
          id: w.id,
          title: w.title,
          code: w.code || '',
          summary: w.summary || '',
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
        await fetch(apiUrl(`/api/widget/${w.id}/`), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
      } else {
        const r = await fetch(apiUrl(`/api/dashboard/${this.dashboardId}/widgets/`), {
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
        try { await fetch(apiUrl(`/api/widget/${id}/`), { method: 'DELETE' }); } catch (e) {}
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
      // No debe colapsar a []: eso destruiría/recrearía los <select> del drawer
      // (y sus <option>) en cada apertura.
      const WidgetClass = this.editingType ? WidgetRegistry.get(this.editingType) : BaseWidget;
      return WidgetClass.drawerFields;
    },

    get drawerHelp() {
      const WidgetClass = this.editingType ? WidgetRegistry.get(this.editingType) : BaseWidget;
      return WidgetClass.help;
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
      this.drawerUtilsOpen = false;
      this.drawerHelpOpen = false;
    },

    async generateWidgetCode() {
      if (!this.drawerDraft.prompt) return;
      this.drawerGenerating = true;
      this.drawerGenerateError = '';
      try {
        const { r, data } = await fetchJsonSafe(apiUrl(`/api/dashboard/${this.dashboardId}/generate-widget-code/`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt: this.drawerDraft.prompt,
            widget_id: this.editingId > 0 ? this.editingId : null,
            chart_type: this.editingType,
            existing_code: this.drawerDraft.code,
          }),
        });
        if (!r.ok || !data) {
          throw new Error((data && data.error) || 'El servidor no respondió correctamente (puede que la IA haya tardado demasiado). Intenta de nuevo.');
        }
        this.drawerDraft.code = data.code;
        if (data.field) this.drawerDraft.filterField = data.field;
        this.drawerDraft.prompt = '';
      } catch (e) {
        this.drawerGenerateError = e.name === 'AbortError'
          ? 'La IA tardó demasiado en responder. Intenta de nuevo.'
          : e.message;
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

    openUtilsPanel() {
      this.utilsOpen = true;
      this.loadUtils();
    },

    closeUtilsPanel() {
      this.utilsOpen = false;
      this.utilDraft = null;
      this.utilGenerateError = '';
    },

    newUtilDraft() {
      this.utilDraft = { id: null, prompt: '', name: '', signature: '', category: '', description: '', source_code: '' };
      this.utilGenerateError = '';
    },

    editUtilDraft(u) {
      this.utilDraft = {
        id: u.id, prompt: '', name: u.name, signature: u.signature,
        category: u.category, description: u.description, source_code: u.source_code,
      };
      this.utilGenerateError = '';
    },

    cancelUtilDraft() {
      this.utilDraft = null;
      this.utilGenerateError = '';
    },

    async generateUtil() {
      if (!this.utilDraft || !this.utilDraft.prompt) return;
      this.utilGenerating = true;
      this.utilGenerateError = '';
      try {
        const { r, data } = await fetchJsonSafe(apiUrl(`/api/dashboard/${this.dashboardId}/utils/generate/`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt: this.utilDraft.prompt,
            existing_util: this.utilDraft.id
              ? { name: this.utilDraft.name, source_code: this.utilDraft.source_code }
              : null,
          }),
        });
        if (!r.ok || !data) {
          throw new Error((data && data.error) || 'El servidor no respondió correctamente (puede que la IA haya tardado demasiado). Intenta de nuevo.');
        }
        Object.assign(this.utilDraft, {
          name: data.name, signature: data.signature,
          category: data.category, description: data.description, source_code: data.source_code,
        });
        this.utilDraft.prompt = '';
      } catch (e) {
        this.utilGenerateError = e.name === 'AbortError'
          ? 'La IA tardó demasiado en responder. Intenta de nuevo.'
          : e.message;
      } finally {
        this.utilGenerating = false;
      }
    },

    async saveUtilDraft() {
      const draft = this.utilDraft;
      if (!draft || !draft.source_code) return;
      const body = {
        name: draft.name, signature: draft.signature,
        category: draft.category, description: draft.description, source_code: draft.source_code,
      };
      try {
        const r = draft.id
          ? await fetch(apiUrl(`/api/util-function/${draft.id}/`), {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body),
            })
          : await fetch(apiUrl(`/api/dashboard/${this.dashboardId}/utils/`), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body),
            });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || 'Error guardando la función');
      } catch (e) {
        this.utilGenerateError = e.message;
        return;
      }
      this.utilDraft = null;
      await this.loadUtils();
    },

    async deleteUtil(u) {
      if (!confirm(`¿Eliminar la función "${u.name}"? Los widgets que la usen fallarán.`)) return;
      try {
        await fetch(apiUrl(`/api/util-function/${u.id}/`), { method: 'DELETE' });
      } catch (e) {}
      await this.loadUtils();
    },

    openCalcColsPanel() {
      this.calcColsOpen = true;
      this.loadCalculatedColumns();
      this.loadAvailableTables();
    },

    closeCalcColsPanel() {
      this.calcColsOpen = false;
      this.calcColDraft = null;
      this.calcColGenerateError = '';
    },

    newCalcColDraft() {
      this.calcColDraft = { id: null, table_name: '', prompt: '', column_name: '', expression: '', description: '' };
      this.calcColGenerateError = '';
    },

    editCalcColDraft(cc) {
      this.calcColDraft = {
        id: cc.id, table_name: cc.table_name, prompt: '',
        column_name: cc.column_name, expression: cc.expression, description: cc.description,
      };
      this.calcColGenerateError = '';
    },

    cancelCalcColDraft() {
      this.calcColDraft = null;
      this.calcColGenerateError = '';
    },

    async generateCalcCol() {
      const draft = this.calcColDraft;
      if (!draft || !draft.prompt || !draft.table_name) return;
      this.calcColGenerating = true;
      this.calcColGenerateError = '';
      try {
        const { r, data } = await fetchJsonSafe(apiUrl(`/api/dashboard/${this.dashboardId}/calculated-columns/generate/`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            table_name: draft.table_name,
            prompt: draft.prompt,
            existing: draft.id
              ? { column_name: draft.column_name, expression: draft.expression }
              : null,
          }),
        });
        if (!r.ok || !data) {
          throw new Error((data && data.error) || 'El servidor no respondió correctamente (puede que la IA haya tardado demasiado). Intenta de nuevo.');
        }
        Object.assign(draft, {
          column_name: data.column_name, expression: data.expression, description: data.description,
        });
        draft.prompt = '';
      } catch (e) {
        this.calcColGenerateError = e.name === 'AbortError'
          ? 'La IA tardó demasiado en responder. Intenta de nuevo.'
          : e.message;
      } finally {
        this.calcColGenerating = false;
      }
    },

    async saveCalcColDraft() {
      const draft = this.calcColDraft;
      if (!draft || !draft.expression || !draft.table_name) return;
      const body = {
        table_name: draft.table_name, column_name: draft.column_name,
        expression: draft.expression, description: draft.description,
      };
      try {
        const r = draft.id
          ? await fetch(apiUrl(`/api/calculated-column/${draft.id}/`), {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body),
            })
          : await fetch(apiUrl(`/api/dashboard/${this.dashboardId}/calculated-columns/`), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body),
            });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || 'Error guardando la columna calculada');
      } catch (e) {
        this.calcColGenerateError = e.message;
        return;
      }
      this.calcColDraft = null;
      await this.loadCalculatedColumns();
    },

    async deleteCalcCol(cc) {
      if (!confirm(`¿Eliminar la columna calculada "${cc.column_name}"? Los widgets que la usen dejarán de tenerla disponible.`)) return;
      try {
        await fetch(apiUrl(`/api/calculated-column/${cc.id}/`), { method: 'DELETE' });
      } catch (e) {}
      await this.loadCalculatedColumns();
    },
  });
});
