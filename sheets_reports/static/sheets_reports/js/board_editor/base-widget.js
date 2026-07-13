(function () {
  class BaseWidget {
    static type = null;
    static palette = {
      icon: '❔',
      label: 'Widget',
      description: '',
      chipClass: 'bg-slate-50/60 border border-slate-200 hover:bg-slate-100/80',
      titleClass: 'text-slate-950',
      descClass: 'text-slate-700/80',
    };
    static defaults = { title: 'Widget', width: 'col-span-6', height: 300 };
    static minHeight = 150;

    static getGhostSpan() {
      const m = /col-span-(\d+)/.exec(this.defaults.width);
      return m ? parseInt(m[1], 10) : 6;
    }

    static dragHandleHTML() {
      return `<div class="drag-handle cursor-move text-ink/30 hover:text-ink/60 absolute left-1 top-0 bottom-0 flex items-center opacity-0 group-hover:opacity-100 transition-opacity z-20 text-[1rem] leading-none">⣿</div>`;
    }

    static actionButtonsHTML() {
      return `<div class="absolute -top-2.5 -right-2.5 flex items-center space-x-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-white border border-line rounded-md shadow-sm px-1 py-0.5 z-30">
        <button class="edit-widget-btn text-ink/40 hover:text-moss-600 transition cursor-pointer p-0.5">
          <svg viewBox="0 0 14 14" class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10.5 1.5a1.41 1.41 0 0 1 2 2L4.5 11.5l-3 1 1-3Z"/>
          </svg>
        </button>
        <button class="delete-widget-btn text-ink/40 hover:text-red-600 transition cursor-pointer p-0.5">
          <svg viewBox="0 0 14 14" class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 3l8 8M11 3l-8 8"/>
          </svg>
        </button>
      </div>`;
    }

    constructor(raw = {}) {
      const defaults = this.constructor.defaults;
      this.id = raw.id;
      this.title = raw.title ?? defaults.title;
      this.chart_type = this.constructor.type;
      this.functionPath = raw.functionPath || '';
      this.width = raw.width || defaults.width;
      this.height = raw.height ?? defaults.height;
      this.startCol = raw.startCol || '';
      this.order = raw.order ?? 0;
      this._dirty = raw._dirty ?? false;
      this._loading = false;
      this.el = null;
      this._chart = null;
    }

    buildElement() {
      throw new Error(`${this.constructor.name}: buildElement() no implementado`);
    }

    renderContent(container, data) {
      throw new Error(`${this.constructor.name}: renderContent() no implementado`);
    }

    loaderOverlayHTML() {
      return `<div class="widget-loader absolute inset-0 bg-white/80 flex items-center justify-center rounded-xl z-30 hidden">
        <svg class="animate-spin h-5 w-5 text-moss-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      </div>`;
    }

    buildStandardCardElement() {
      const el = document.createElement('div');
      el.className = `${this.width}${this.startCol ? ' ' + this.startCol : ''} bg-white border border-line rounded-xl shadow-sm p-4 flex flex-col justify-between relative group`;
      el.style.height = this.height + 'px';
      el.dataset.widgetId = this.id;
      el.dataset.type = this.chart_type;
      el.innerHTML = `
        ${BaseWidget.dragHandleHTML()}
        <div class="flex justify-between items-center border-b border-line pb-2 mb-2 select-none">
          <span class="title-display text-[10px] font-bold uppercase tracking-wider text-ink/40">${this.title}</span>
        </div>
        <div id="chart-${this.id}" class="flex-1 w-full min-h-0"></div>
        ${this.loaderOverlayHTML()}
        ${BaseWidget.actionButtonsHTML()}
        <div class="resize-handle absolute bottom-1 right-1 w-4 h-4 cursor-se-resize z-10 opacity-60 hover:opacity-100 transition">
          <svg viewBox="0 0 10 10" class="w-full h-full text-ink/30" fill="none">
            <line x1="2" y1="8" x2="8" y2="2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            <line x1="4" y1="8" x2="8" y2="4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>`;
      return el;
    }

    mount() {
      this.el = this.buildElement();
      this._attachCommonEvents();
      const container = this.getContentContainer();
      if (container) {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => this.renderContent(container));
        });
      }
      return this.el;
    }

    getContentContainer() {
      return this.el ? this.el.querySelector(`#chart-${this.id}`) : null;
    }

    setLoading(isLoading) {
      this._loading = isLoading;
      const loader = this.el && this.el.querySelector('.widget-loader');
      if (loader) loader.classList.toggle('hidden', !isLoading);
    }

    updateChrome() {
      if (!this.el) return;
      const titleEl = this.el.querySelector('.title-display');
      if (titleEl) titleEl.textContent = this.title;

      Array.from(this.el.classList).filter(c => c.startsWith('col-start-')).forEach(c => this.el.classList.remove(c));
      ['col-span-3', 'col-span-4', 'col-span-6', 'col-span-8', 'col-span-12'].forEach(c => this.el.classList.remove(c));
      this.el.classList.add(this.width);
      if (this.startCol) this.el.classList.add(this.startCol);
      this.el.style.height = this.height + 'px';

      window.dispatchEvent(new Event('resize'));
    }

    getProperties() {
      return { width: this.width, height: this.height, startCol: this.startCol };
    }

    toPayload() {
      return {
        title: this.title,
        chart_type: this.chart_type,
        function_path: this.functionPath,
        properties: this.getProperties(),
        order: this.order,
      };
    }

    renderApexChart(container, options) {
      if (this._chart) {
        this._chart.destroy();
        this._chart = null;
      }
      container.innerHTML = '';
      this._chart = new ApexCharts(container, options);
      this._chart.render();
    }

    async fetchAndRender() {
      if (!this.functionPath || this.id < 0) return;
      this.setLoading(true);
      try {
        const r = await fetch(`/api/widget/${this.id}/data/`);
        const data = await r.json();
        const container = this.getContentContainer();
        if (container) this.renderContent(container, data);
      } catch (e) {
        // silencioso, igual que el comportamiento anterior
      } finally {
        this.setLoading(false);
      }
    }

    _attachCommonEvents() {
      const el = this.el;
      el.querySelector('.edit-widget-btn').addEventListener('click', () => {
        Alpine.store('dashboard').openDrawer(this.id);
      });

      el.querySelector('.delete-widget-btn').addEventListener('click', () => {
        Alpine.store('dashboard').removeWidget(this.id);
        el.remove();
      });

      const resizeHandle = el.querySelector('.resize-handle');
      if (resizeHandle) resizeHandle.addEventListener('mousedown', (e) => this._onResizeStart(e));
    }

    _onResizeStart(e) {
      e.preventDefault();
      e.stopPropagation();

      const el = this.el;
      const minHeight = this.constructor.minHeight;
      const startY = e.clientY;
      const startHeight = el.offsetHeight;

      function onMouseMove(ev) {
        const newHeight = Math.max(minHeight, startHeight + (ev.clientY - startY));
        el.style.height = newHeight + 'px';
        window.dispatchEvent(new Event('resize'));
      }

      function onMouseUp() {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
      }

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    }
  }

  window.BaseWidget = BaseWidget;
})();
