(function () {
  class KpiWidget extends BaseWidget {
    static type = 'kpi';
    static palette = {
      icon: '🔢',
      label: 'Tarjeta KPI',
      description: 'Indicador numérico único',
      chipClass: 'bg-emerald-50/60 border border-emerald-200 hover:bg-emerald-100/80',
      titleClass: 'text-emerald-950',
      descClass: 'text-emerald-700/80',
    };
    static defaults = { title: 'Tarjeta KPI', width: 'col-span-4', height: 300 };

    static mockData() {
      return { total_ventas: 412900, label: 'Monto Consumido' };
    }

    buildElement() {
      return this.buildStandardCardElement();
    }

    renderContent(container, data) {
      const payload = data || this.constructor.mockData();
      const value = payload.total_ventas ?? '—';
      const label = payload.label ?? 'Total';
      container.className = 'flex flex-col items-center justify-center h-full pb-3';
      container.innerHTML = `
        <span class="text-2xl font-black text-ink tracking-tight">${Number(value).toLocaleString()}</span>
        <span class="text-[11px] font-semibold text-ink/40 mt-0.5 uppercase tracking-wide">${label}</span>
      `;
    }
  }

  WidgetRegistry.register(KpiWidget);
})();
