(function () {
  class DonutWidget extends BaseWidget {
    static type = 'donut';
    static palette = {
      icon: '🍩',
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
        series,
        labels,
        legend: { position: 'bottom', fontSize: '11px' },
      };
      this.renderApexChart(container, options);
    }
  }

  WidgetRegistry.register(DonutWidget);
})();
