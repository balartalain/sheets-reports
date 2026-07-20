(function () {
  class BarWidget extends BaseWidget {
    static type = 'bar';
    static palette = {
      icon: '📊',
      label: 'Gráfico de Barras',
      description: 'Comparativas grupales',
      chipClass: 'bg-blue-50/60 border border-blue-200 hover:bg-blue-100/80',
      titleClass: 'text-blue-950',
      descClass: 'text-blue-700/80',
    };
    static defaults = { title: 'Gráfico de Barras', width: 'md:col-span-6', height: 300 };
    static help = 'Compara valores entre categorías usando barras: una o más series de datos ' +
      '(ej. ventas por mes, participantes por carrera) agrupadas o apiladas a lo largo de un eje ' +
      'de categorías. Ideal para comparar magnitudes entre grupos, no para ver tendencias continuas.';

    static FIELD_HORIZONTAL = { key: 'horizontal', label: 'Horizontal', type: 'checkbox' };

    static get drawerFields() {
      return [...super.drawerFields,
        this.FIELD_HORIZONTAL,
        { key: 'yAxisWidth', label: 'Ancho del Eje Y (px)', type: 'number', min: 100, step: 10 },
        { key: 'stacked', label: 'Apilado', type: 'checkbox' },
        { key: 'dataLabelFormatter', label: 'Formato de Etiquetas de Datos. Ej. {value} %', type: 'text' },
        { key: 'chartWidth', label: 'Forzar ancho de gráfico', type: 'number', min: 100, step: 50 },
      ];
    }

    static mockData() {
      return {
        series: [{ name: 'Ejecutado', data: [14200, 19800, 8500, 11000, 6400, 15000] }],
        categories: ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun'],
      };
    }

    constructor(raw) {
      super(raw);
      this.horizontal = raw.horizontal ?? false;
      this.yAxisWidth = raw.yAxisWidth;
      this.stacked = raw.stacked ?? false;
      this.dataLabelFormatter = raw.dataLabelFormatter;
      this.chartWidth = raw.chartWidth;
    }

    buildElement() {
      return this.buildStandardCardElement();
    }

    buildReadOnlyElement() {
      const el = super.buildReadOnlyElement();
      el.querySelector('.actions-slot').innerHTML = this.downloadButtonHTML('Descargar CSV');
      return el;
    }

    getProperties() {
      return { ...super.getProperties(),
        horizontal: this.horizontal,
        yAxisWidth: this.yAxisWidth,
        stacked: this.stacked,
        dataLabelFormatter: this.dataLabelFormatter,
        chartWidth: this.chartWidth,
      };
    }

    renderContent(container, data) {
      const payload = data || this.constructor.mockData();
      const series = payload.series || [{ name: 'Datos', data: [] }];
      const categories = payload.categories || [];

      if (this.chartWidth) {
        container.style.overflowX = 'scroll';
        container.style.overflowY = 'scroll';
      } else {
        container.style.overflowX = '';
        container.style.overflowY = '';
      }

      const options = {
        chart: { type: 'bar', stacked: this.stacked, height: '90%', width: this.chartWidth || '100%', fontFamily: 'inherit', toolbar: { show: false } },
        colors: ['#2563eb', '#f5a623', '#00e1ffff', '#3965c4ff'],
        series,
        xaxis: { categories, labels: { style: { fontSize: '11px' }, maxHeight: 150 } },
        plotOptions: { bar: { horizontal: this.horizontal, borderRadius: 4, borderRadiusApplication: 'end', columnWidth: '50%',
          dataLabels:{
            position: 'center'
          }
        }},
        //grid: { padding: { bottom: 25 } },
        dataLabels: {
          enabled: true,
          formatter: (val) => {
            return this.dataLabelFormatter ? this.dataLabelFormatter.replace('{value}', val) : val;
          },
          background: {
              enabled: true,
              foreColor: '#fff',     // Color del texto DENTRO del fondo (Blanco)
              padding: 4,            // Espaciado interno del fondo
              borderRadius: 4,       // Bordes redondeados del fondo
              borderWidth: 1,        // Grosor del borde
              borderColor: '#111',   // Color del borde del fondo
              opacity: 0.9,          // Opacidad del fondo
              dropShadow: {          // Añade una pequeña sombra al fondo si quieres
                enabled: false
              }
            },
          style: {
            fontSize: '11px',
            colors: ['#333'],
          },
          dropShadow: {
            enabled: true,    // ¡Activa la sombra nativa!
            top: 1,           // Desplazamiento vertical de la sombra
            left: 1,          // Desplazamiento horizontal de la sombra
            blur: 1,          // Qué tan difuminada está la sombra
            color: '#000000', // Color de la sombra (negro)
            opacity: 0.7      // Opacidad (0 es transparente, 1 es oscuro total)
          }
        },
        stroke: {
          show: true,
          width: 1,
          colors: ['#fff'],
        },
        tooltip: {
          shared: true,
          intersect: false,
        },
        yaxis: {
          labels: {
            ...(this.yAxisWidth && { maxWidth: this.yAxisWidth }),
          }
        },
      };
      this.renderApexChart(container, options);

      const downloadBtn = this.el && this.el.querySelector('.download-csv-btn');
      if (downloadBtn) {
        downloadBtn.onclick = () => {
          const headers = ['Categoría', ...series.map(s => s.name)];
          const rows = categories.map((cat, i) => [cat, ...series.map(s => s.data[i])]);
          this.downloadRowsAsCSV(headers, rows, `${this._filenameSlug('grafico')}.csv`);
        };
      }
    }
  }

  WidgetRegistry.register(BarWidget);
})();
