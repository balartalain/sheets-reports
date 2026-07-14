(function () {
  class TableWidget extends BaseWidget {
    static type = 'table';
    static palette = {
      icon: '<svg viewBox="0 0 20 20" width="1.25rem" height="1.25rem" class="inline-block" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2.5" y="3.5" width="15" height="13" rx="1.5"/><line x1="2.5" y1="8" x2="17.5" y2="8"/><line x1="2.5" y1="12.5" x2="17.5" y2="12.5"/><line x1="8.5" y1="3.5" x2="8.5" y2="16.5"/></svg>',
      label: 'Tabla',
      description: 'Filas y columnas de datos',
      chipClass: 'bg-amber-50/60 border border-amber-200 hover:bg-amber-100/80',
      titleClass: 'text-amber-950',
      descClass: 'text-amber-700/80',
    };
    static defaults = { title: 'Tabla', width: 'col-span-6', height: 300 };

    static FIELD_PAGE_SIZE = { key: 'pageSize', label: 'Filas por página', type: 'number', min: 5, step: 5 };

    static get drawerFields() {
      return [...super.drawerFields, this.FIELD_PAGE_SIZE];
    }

    static mockData() {
      return {
        columns: [
          { title: 'Producto', field: 'Producto' },
          { title: 'Vendedor', field: 'Vendedor' },
          { title: 'Ventas', field: 'Ventas' },
        ],
        rows: [
          { Producto: 'Producto A', Vendedor: 'Cajero 1', Ventas: 14200 },
          { Producto: 'Producto B', Vendedor: 'Cajero 2', Ventas: 19800 },
          { Producto: 'Producto C', Vendedor: 'Cajero 3', Ventas: 8500 },
        ],
      };
    }

    constructor(raw) {
      super(raw);
      this.pageSize = raw.pageSize ?? 10;
    }

    getProperties() {
      return { ...super.getProperties(), pageSize: this.pageSize };
    }

    buildElement() {
      return this.buildStandardCardElement();
    }

    renderContent(container, data) {
      const payload = data || this.constructor.mockData();
      if (this._table) {
        this._table.destroy();
        this._table = null;
      }
      container.innerHTML = '';
      container.style.backgroundColor = '#fff';
      this._table = new Tabulator(container, {
        data: payload.rows || [],
        columns: payload.columns || [],
        layout: 'fitColumns',
        pagination: true,
        paginationSize: this.pageSize,
        height: '100%',
      });
    }

    destroy() {
      if (this._table) {
        this._table.destroy();
        this._table = null;
      }
      super.destroy();
    }
  }

  WidgetRegistry.register(TableWidget);
})();
