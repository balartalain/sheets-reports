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
    static defaults = { title: 'Filtro', width: 'col-span-4', height: 48 };

    static mockData() {
      return [2021, 2022, 2023];
    }

    constructor(raw) {
      super(raw);
      this.field = raw.field || '';
      this._selectedValue = '';
    }

    getProperties() {
      return { ...super.getProperties(), field: this.field };
    }

    buildElement() {
      const el = document.createElement('div');
      el.className = `${this.width}${this.startCol ? ' ' + this.startCol : ''} relative flex items-center group`;
      el.style.height = this.height + 'px';
      el.style.setProperty('--ghost-span', this._ghostSpanFromWidth());
      el.dataset.widgetId = this.id;
      el.dataset.type = this.chart_type;

      el.innerHTML = `
        ${BaseWidget.dragHandleHTML()}
        <div id="chart-${this.id}" class="flex-1 min-w-0 pl-4"></div>
        ${BaseWidget.actionButtonsHTML()}
        <div class="resize-handle absolute bottom-0 left-0 right-0 h-1.5 cursor-s-resize z-10 opacity-0 group-hover:opacity-60 hover:opacity-100 transition hover:bg-moss-300/40 rounded-b-lg"></div>
      `;
      return el;
    }

    buildReadOnlyElement() {
      const el = document.createElement('div');
      el.className = `${this.width}${this.startCol ? ' ' + this.startCol : ''} relative flex items-center`;
      el.style.height = this.height + 'px';
      el.dataset.widgetId = this.id;
      el.dataset.type = this.chart_type;
      el.innerHTML = `<div id="chart-${this.id}" class="flex-1 min-w-0"></div>`;
      return el;
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

      const labelHTML = this.field
        ? `<span class="text-[11px] font-semibold text-ink/40 mr-2 whitespace-nowrap">${BaseWidget.escapeHTML(this.field)}</span>`
        : '';

      container.innerHTML = `
        <div class="flex items-center w-full gap-2">
          ${labelHTML}
          <select class="flex-1 min-w-0 text-sm border border-line rounded-lg px-3 py-2 bg-white focus:outline-none focus:border-moss-500">
            <option value="">Seleccione...</option>
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
      if (!this.field) return;
      const dashboardId = Alpine.store('dashboard').dashboardId;
      try {
        await fetch(`/api/dashboard/${dashboardId}/filters/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ field: this.field, value }),
        });
      } catch (e) {
        // silencioso, igual que el resto de las llamadas fetch en este archivo
      }
      window.dispatchEvent(new CustomEvent('dashboard:filters-changed', { detail: { field: this.field, value } }));
    }
  }

  WidgetRegistry.register(FilterWidget);
})();
