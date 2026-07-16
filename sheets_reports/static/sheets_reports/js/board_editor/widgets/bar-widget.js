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
    static defaults = { title: 'Gráfico de Barras', width: 'col-span-6', height: 300 };

    static FIELD_HORIZONTAL = { key: 'horizontal', label: 'Horizontal', type: 'checkbox' };

    static get drawerFields() {
      return [...super.drawerFields, this.FIELD_HORIZONTAL];
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
    }

    buildElement() {
      return this.buildStandardCardElement();
    }

    getProperties() {
      return { ...super.getProperties(), horizontal: this.horizontal };
    }

    renderContent(container, data) {
      const payload = data || this.constructor.mockData();
      const series = payload.series || [{ name: 'Datos', data: [] }];
      const categories = payload.categories || [];
      const options = {
        chart: { type: 'bar', height: '100%', width: '100%', fontFamily: 'inherit', toolbar: { show: false } },
        colors: ['#2563eb', '#f5a623', '#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe', '#dbeafe'],
        series,
        xaxis: { categories, labels: { style: { fontSize: '11px' } } },
        plotOptions: { bar: { horizontal: this.horizontal, borderRadius: 4, borderRadiusApplication: 'end', columnWidth: '50%' } },
        grid: { padding: { bottom: 25 } },
        stroke: {
          show: true,
          width: 1,
          colors: ['#fff'],
        },
        tooltip: {
          shared: true,
          intersect: false,
        },
      };
      this.renderApexChart(container, options);
    }
  }

  WidgetRegistry.register(BarWidget);
})();
