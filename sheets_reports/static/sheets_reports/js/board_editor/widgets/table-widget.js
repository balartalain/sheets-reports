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
    static defaults = { title: 'Tabla', width: 'md:col-span-6', height: 300 };

    static FIELD_PAGE_SIZE = { key: 'pageSize', label: 'Filas por página', type: 'number', min: 5, step: 5 };
    static FIELD_SHOW_PAGINATION = { key: 'showPagination', label: 'Mostrar paginación', type: 'checkbox' };

    static get drawerFields() {
      return [...super.drawerFields,
        this.FIELD_PAGE_SIZE,
        this.FIELD_SHOW_PAGINATION,
        { key: 'boldLastRow', label: 'Resaltar última fila', type: 'checkbox' }
      ];
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
      this.showPagination = raw.showPagination ?? true;
      this.boldLastRow = raw.boldLastRow ?? false;
    }

    getProperties() {
      return { ...super.getProperties(), pageSize: this.pageSize, showPagination: this.showPagination, boldLastRow: this.boldLastRow };
    }

    buildElement() {
      return this.buildStandardCardElement();
    }

    buildReadOnlyElement() {
      const el = super.buildReadOnlyElement();
      el.querySelector('.actions-slot').innerHTML = this.downloadButtonHTML('Descargar CSV');
      return el;
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
        layout: 'fitDataStretch',
        pagination: this.showPagination,
        paginationSize: this.pageSize,
        height: '100%',
        rowFormatter: (row)=> {
          // Quitamos la clase por defecto para evitar residuos al alternar el checkbox
          row.getElement().classList.remove("tabulator-row-bold");

          // Si la opción está activa y es la última fila del set de datos actual
          if (this.boldLastRow) {
            const todasLasFilas = row.getTable().getRows("active"); // Obtiene las filas activas/filtradas
            const ultimaFila = todasLasFilas[todasLasFilas.length - 1];

            // Si la fila actual que se está dibujando es idéntica a la última fila
            if (ultimaFila && row.getPosition() === ultimaFila.getPosition()) {
              row.getElement().classList.add("tabulator-row-bold");
            }
          }
        }
      });

      const downloadBtn = this.el && this.el.querySelector('.download-csv-btn');
      if (downloadBtn) {
        downloadBtn.onclick = () => {
          this._table.download('csv', `${this._filenameSlug('tabla')}.csv`);
        };
      }
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
