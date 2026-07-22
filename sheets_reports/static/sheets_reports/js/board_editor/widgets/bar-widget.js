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
        { key: 'showGrid', label: 'Mostrar cuadrícula', type: 'checkbox' },
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
      this.showGrid = raw.showGrid ?? false;
    }

    buildElement() {
      return this.buildStandardCardElement();
    }

    getProperties() {
      return { ...super.getProperties(),
        horizontal: this.horizontal,
        yAxisWidth: this.yAxisWidth,
        stacked: this.stacked,
        dataLabelFormatter: this.dataLabelFormatter,
        chartWidth: this.chartWidth,
        showGrid: this.showGrid,
      };
    }

    renderContent(container, data) {
      const payload = data || this.constructor.mockData();
      const series = payload.series || [{ name: 'Datos', data: [] }];
      const categories = payload.categories || [];

      if (this.chartWidth) {
        container.style.overflowX = 'scroll';
        container.style.overflowY = '';
      } else {
        container.style.overflowX = '';
        container.style.overflowY = '';
      }

      const options = {
        chart: { type: 'bar', stacked: this.stacked, height: '90%', width: this.chartWidth || '100%', fontFamily: 'inherit', toolbar: this.chartExportToolbar() },
        colors: ['#2563eb', '#f5a623', '#00e1ffff', '#8b5cf6'],
        series,
        xaxis: {
          categories: categories.map((cat) => formatearEtiquetaApex(cat, 18)), // Llama a la función para formatear las etiquetas
          labels: {
            rotate: 0,        // Mantiene el texto horizontal (sin inclinar)
            align: 'center',  // Centra las líneas de texto entre sí
            style: {
              fontSize: '12px',
              cssClass: 'apexcharts-xaxis-label-centered'
            }
          },
          maxHeight: 150
        },
        plotOptions: { bar: { horizontal: this.horizontal, borderRadius: 4, borderRadiusApplication: 'end',
          dataLabels:{
            position: 'top'
          }
        }},
        grid: {
          show: this.showGrid
        },
        dataLabels: {
          enabled: true,
          formatter: (val) => {
            return this.dataLabelFormatter ? this.dataLabelFormatter.replace('{value}', val) : val;
          },
          //crop: false,
          offsetY: !this.horizontal ? -20 : 0,
          offsetX: this.horizontal ? 20 : 0,
          // background: {
          //     enabled: true,
          //     foreColor: '#fff',     // Color del texto DENTRO del fondo (Blanco)
          //     padding: 4,            // Espaciado interno del fondo
          //     borderRadius: 4,       // Bordes redondeados del fondo
          //     borderWidth: 1,        // Grosor del borde
          //     borderColor: '#111',   // Color del borde del fondo
          //     opacity: 0.9,          // Opacidad del fondo
          //     dropShadow: {          // Añade una pequeña sombra al fondo si quieres
          //       enabled: false
          //     }
          //   },
          style: {
            fontSize: '11px',
            colors: ['#333'],
          },
          dropShadow: {
            enabled: false,    // ¡Activa la sombra nativa!
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
          },
          max: (max) => max * 1.12,
        },
      };
      this.renderApexChart(container, options);
    }
  }

  WidgetRegistry.register(BarWidget);
})();
