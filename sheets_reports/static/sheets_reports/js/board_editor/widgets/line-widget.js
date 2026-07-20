(function () {
  class LineWidget extends BaseWidget {
    static type = 'line';
    static palette = {
      icon: '📈',
      label: 'Gráfico de Líneas',
      description: 'Tendencias en el tiempo',
      chipClass: 'bg-purple-50/60 border border-purple-200 hover:bg-purple-100/80',
      titleClass: 'text-purple-950',
      descClass: 'text-purple-700/80',
    };
    static defaults = { title: 'Gráfico de Líneas', width: 'md:col-span-6', height: 300 };
    static help = 'Muestra la evolución de uno o más valores a lo largo de un eje continuo, ' +
      'normalmente tiempo (ej. inscripciones por mes, ingresos por semana). Ideal para ver ' +
      'tendencias, picos y caídas a lo largo del período.';

    static mockData() {
      return {
        series: [{ name: 'Tendencia', data: [45, 52, 38, 65, 59, 87] }],
        categories: ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun'],
      };
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
      const series = payload.series || [{ name: 'Datos', data: [] }];
      const categories = payload.categories || [];
      const options = {
        chart: { type: 'line', height: '100%', width: '100%', fontFamily: 'inherit', toolbar: { show: false } },
        colors: ['#7c3aed'],
        stroke: { curve: 'smooth', width: 3 },
        series,
        xaxis: { categories, labels: { style: { fontSize: '11px' } } },
        grid: { padding: { bottom: 25 } },
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

  WidgetRegistry.register(LineWidget);
})();
