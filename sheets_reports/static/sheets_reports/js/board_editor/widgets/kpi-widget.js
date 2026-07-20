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
    static defaults = { title: 'Tarjeta KPI', width: 'md:col-span-4', height: 300 };
    static help = 'Resalta un único número clave (ej. total recaudado, matrícula total) como ' +
      'cifra grande y protagonista, con etiqueta descriptiva y, opcionalmente, uno o más valores ' +
      'secundarios de contexto debajo (ej. desglose por método de pago). No compara categorías ' +
      'ni muestra tendencias: para eso usa un gráfico de barras o líneas.';

    static mockData() {
      return {
        main_value: 412900,
        main_label: 'Monto Consumido',
        secondary_values: [
          { label: 'Efectivo', value: 210000 },
          { label: 'Tarjeta', value: 202900 },
        ],
      };
    }

    buildElement() {
      return this.buildStandardCardElement();
    }

    renderContent(container, data) {
      const payload = data || this.constructor.mockData();
      const value = payload.main_value ?? '—';
      const label = payload.main_label ?? 'Total';
      const secondaryValues = payload.secondary_values || [];
      const secondaryHTML = secondaryValues.length
        ? `<div class="flex flex-col items-center mt-2 gap-0.5">
            ${secondaryValues.map(({ label, value }) => {
              const formattedValue = typeof value === 'number' ? value.toLocaleString() : value;
              return `<span class="text-[10px] text-ink/60">${formattedValue} ${label}</span>`;
            }).join('')}
          </div>`
        : '';
      container.className = 'flex flex-col items-center justify-center h-full pb-3';
      container.innerHTML = `
        <span class="text-2xl font-black text-ink tracking-tight">${Number(value).toLocaleString()}</span>
        <span class="text-[11px] font-semibold text-ink/40 mt-0.5 uppercase tracking-wide">${label}</span>
        ${secondaryHTML}
      `;
    }
  }

  WidgetRegistry.register(KpiWidget);
})();
