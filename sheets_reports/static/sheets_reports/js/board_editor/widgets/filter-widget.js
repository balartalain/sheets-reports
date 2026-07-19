(function () {
  class FilterWidget extends BaseWidget {
    static type = 'filter';
    static minHeight = 44;
    static palette = {
      icon: '🔽',
      label: 'Filtro',
      description: 'Selector de criterios',
      chipClass: 'bg-amber-50/60 border border-amber-200 hover:bg-amber-100/80',
      titleClass: 'text-amber-950',
      descClass: 'text-amber-700/80',
    };
    static defaults = { title: 'Filtro', width: 'md:col-span-4' };

    static FIELD_FILTER_FIELD = {
      key: 'filterField',
      label: 'Campo a filtrar (nombre exacto de la columna)',
      type: 'text',
    };

    static get drawerFields() {
      const base = super.drawerFields.filter(field => field.key !== 'height');
      const titleIdx = base.findIndex(f => f.key === 'title');
      return [...base.slice(0, titleIdx + 1), this.FIELD_FILTER_FIELD, ...base.slice(titleIdx + 1)];
    }

    static mockData() {
      return [2021, 2022, 2023];
    }

    constructor(raw) {
      super(raw);
      this.filterField = raw.filterField || '';
      this._selectedValue = '';
    }

    getProperties() {
      return { ...super.getProperties(), filterField: this.filterField };
    }

    buildElement() {
      const el = document.createElement('div');
      el.className = `col-span-12 ${this.width}${this.startCol ? ' ' + this.startCol : ''} relative flex items-center group self-start`;
      //el.style.height = this.height + 'px';
      el.style.setProperty('--ghost-span', this._ghostSpanFromWidth());
      el.dataset.widgetId = this.id;
      el.dataset.type = this.chart_type;

      el.innerHTML = `
        ${BaseWidget.dragHandleHTML()}
        <div id="chart-${this.id}" class="flex-1 min-w-0"></div>
        ${BaseWidget.actionButtonsHTML()}
      `;
      return el;
    }

    buildReadOnlyElement() {
      const el = document.createElement('div');
      el.className = `col-span-12 ${this.width}${this.startCol ? ' ' + this.startCol : ''} relative flex items-center self-start`;
      el.dataset.widgetId = this.id;
      el.dataset.type = this.chart_type;
      el.innerHTML = `<div id="chart-${this.id}" class="flex-1 min-w-0"></div>${this.loaderOverlayHTML()}`;
      return el;
    }

    renderError(message) {
      const container = this.getContentContainer();
      if (!container) return;
      const text = message || 'Error al cargar los datos';
      container.innerHTML = `
        <span class="block w-full text-xs text-red-600 truncate" title="${BaseWidget.escapeHTML(text)}">${BaseWidget.escapeHTML(text)}</span>
      `;
    }

    renderContent(container, data) {
      let items, selected = null;
      if (data && !Array.isArray(data) && typeof data === 'object') {
        items = data.options || [];
        selected = data.selected;
      } else {
        items = data || this.constructor.mockData();
      }
      if (selected !== null && selected !== undefined && selected !== '') {
        this._selectedValue = String(selected);
      }

      const optionsHTML = items.map(item => {
        const value = (item && typeof item === 'object') ? item.value : item;
        const label = (item && typeof item === 'object') ? (item.label ?? item.value) : item;
        return `<option value="${BaseWidget.escapeHTML(String(value))}">${BaseWidget.escapeHTML(String(label))}</option>`;
      }).join('');

      container.innerHTML = `
        <div class="flex items-center w-full gap-2">
          <select class="flex-1 min-w-0 text-sm border border-line rounded-lg px-3 py-2 bg-white focus:outline-none focus:border-moss-500">
            <option value="">${BaseWidget.escapeHTML(this.title)}</option>
            ${optionsHTML}
          </select>
        </div>
      `;

      const select = container.querySelector('select');
      if (this._selectedValue) select.value = this._selectedValue;
      select.addEventListener('change', () => {
        this._selectedValue = select.value;
        this._onFilterChange(select.value);
      });
    }

    async _onFilterChange(value) {
      if (!this.filterField) return;
      const dashboardId = Alpine.store('dashboard').dashboardId;
      try {
        await fetch(apiUrl(`/api/dashboard/${dashboardId}/filters/`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ field: this.filterField, value }),
        });
      } catch (e) {
        // silencioso, igual que el resto de las llamadas fetch en este archivo
      }
      window.dispatchEvent(new CustomEvent('dashboard:filters-changed', { detail: { field: this.filterField, value } }));
    }
  }

  WidgetRegistry.register(FilterWidget);
})();
