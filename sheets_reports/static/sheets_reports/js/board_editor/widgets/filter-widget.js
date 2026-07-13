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

    buildElement() {
      const el = document.createElement('div');
      el.className = `${this.width}${this.startCol ? ' ' + this.startCol : ''} relative flex items-center group`;
      el.style.height = this.height + 'px';
      el.dataset.widgetId = this.id;
      el.dataset.type = this.chart_type;

      el.innerHTML = `
        ${BaseWidget.dragHandleHTML()}
        <div id="chart-${this.id}" class="flex-1 min-w-0"></div>
        ${BaseWidget.actionButtonsHTML()}
        <div class="resize-handle absolute bottom-0 left-0 right-0 h-1.5 cursor-s-resize z-10 opacity-0 group-hover:opacity-60 hover:opacity-100 transition hover:bg-moss-300/40 rounded-b-lg"></div>
      `;
      return el;
    }

    renderContent(container, data) {
      const items = data || this.constructor.mockData();
      const optionsHTML = items.map(item => {
        const value = (item && typeof item === 'object') ? item.value : item;
        const label = (item && typeof item === 'object') ? (item.label ?? item.value) : item;
        return `<option value="${BaseWidget.escapeHTML(String(value))}">${BaseWidget.escapeHTML(String(label))}</option>`;
      }).join('');

      container.innerHTML = `
        <select class="w-full text-sm border border-line rounded-lg px-3 py-2 bg-white focus:outline-none focus:border-moss-500">
          <option value="">Seleccione...</option>
          ${optionsHTML}
        </select>
      `;
    }
  }

  WidgetRegistry.register(FilterWidget);
})();
