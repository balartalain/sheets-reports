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

    static FIELD_HORIZONTAL = { key: 'horizontal', label: 'Horizontal', type: 'checkbox' };

    static get drawerFields() {
      return [...super.drawerFields,
        this.FIELD_HORIZONTAL,
        { key: 'yAxisWidth', label: 'Ancho del Eje Y (px)', type: 'number', min: 100, step: 10 },
        { key: 'stacked', label: 'Apilado', type: 'checkbox' },
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
    }

    buildElement() {
      return this.buildStandardCardElement();
    }

    getProperties() {
      return { ...super.getProperties(), horizontal: this.horizontal, yAxisWidth: this.yAxisWidth, stacked: this.stacked };
    }

    renderContent(container, data) {
      const payload = data || this.constructor.mockData();
      const series = payload.series || [{ name: 'Datos', data: [] }];
      const categories = payload.categories || [];
      const options = {
        chart: { type: 'bar', stacked: this.stacked, height: '95%', width: '100%', fontFamily: 'inherit', toolbar: { show: false } },
        colors: ['#2563eb', '#f5a623', '#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe', '#dbeafe'],
        series,
        xaxis: { categories, labels: { style: { fontSize: '11px' } } },
        plotOptions: { bar: { horizontal: this.horizontal, borderRadius: 4, borderRadiusApplication: 'end', columnWidth: '50%' } },
        grid: { padding: { bottom: 25 } },
        dataLabels: {
          enabled: true,
          style: {
            fontSize: '11px',
            colors: ['#fff'],
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
            ...(this.yAxisWidth && { maxWidth: this.yAxisWidth })
          }
        },
      };
      this.renderApexChart(container, options);
    }
  }

  WidgetRegistry.register(BarWidget);
})();
