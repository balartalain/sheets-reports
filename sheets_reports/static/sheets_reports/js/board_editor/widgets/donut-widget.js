(function () {
  class DonutWidget extends BaseWidget {
    static type = 'donut';
    static palette = {
      icon: '<svg viewBox="0 0 20 20" width="1.25rem" height="1.25rem" class="inline-block"><circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" stroke-width="3" opacity="0.25"/><path d="M10 3A7 7 0 1 1 4.5 16" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>',
      label: 'Gráfico de Dona',
      description: 'Proporciones por categoría',
      chipClass: 'bg-rose-50/60 border border-rose-200 hover:bg-rose-100/80',
      titleClass: 'text-rose-950',
      descClass: 'text-rose-700/80',
    };
    static defaults = { title: 'Gráfico de Dona', width: 'col-span-4', height: 300 };

    static mockData() {
      return {
        series: [{ name: 'Ventas', data: [44, 55, 13, 33] }],
        categories: ['Norte', 'Sur', 'Este', 'Oeste'],
      };
    }

    buildElement() {
      return this.buildStandardCardElement();
    }

    renderContent(container, data) {
      const payload = data || this.constructor.mockData();
      const series = (payload.series && payload.series[0] && payload.series[0].data) || [];
      const labels = payload.categories || [];
      const options = {
        chart: { type: 'donut', height: '90%', width: '100%', fontFamily: 'inherit', toolbar: { show: false } },
        colors: ['#2563eb', '#f5a623', '#1F8A5F', '#60a5fa', '#93c5fd', '#bfdbfe', '#dbeafe'],
        series,
        labels,
        legend: { position: 'bottom', fontSize: '11px' },
      };
      this.renderApexChart(container, options);
    }
  }

  WidgetRegistry.register(DonutWidget);
})();
