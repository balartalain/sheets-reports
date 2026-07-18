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
    static defaults = { title: 'Widget', width: 'md:col-span-6', height: 300 };
    static minHeight = 150;

    static FIELD_TITLE = { key: 'title', label: 'Título', type: 'text' };

    static FIELD_FUNCTION_PATH = {
      key: 'functionPath',
      label: 'Función del servidor',
      type: 'select',
      optionsSource: 'flatFunctions',
      optionValueKey: 'path',
      emptyOption: { value: '', label: '— Sin asignar —' },
      refreshable: true,
    };

    static FIELD_WIDTH = {
      key: 'width',
      label: 'Ancho',
      type: 'select',
      options: [
        { value: 'md:col-span-2', label: '17%' },
        { value: 'md:col-span-3', label: '25%' },
        { value: 'md:col-span-4', label: '33%' },
        { value: 'md:col-span-6', label: '50%' },
        { value: 'md:col-span-8', label: '66%' },
        { value: 'md:col-span-12', label: '100%' },
      ],
    };

    static get FIELD_HEIGHT() {
      return { key: 'height', label: 'Alto (px)', type: 'number', min: this.minHeight, step: 10 };
    }

    static FIELD_START_COL = {
      key: 'startCol',
      label: 'Posición en fila',
      type: 'select',
      options: [
        { value: '', label: 'Fluido' },
        { value: 'md:col-start-1', label: 'Al inicio' },
        { value: 'md:col-start-2', label: 'Dejar 1 espacio' },
        { value: 'md:col-start-3', label: 'Dejar 2 espacios' },
        { value: 'md:col-start-4', label: 'Dejar 3 espacios' },
        { value: 'md:col-start-5', label: 'Dejar 4 espacio' },
        { value: 'md:col-start-6', label: 'Dejar 5 espacios' },
        { value: 'md:col-start-7', label: 'Dejar 6 espacios' },
        { value: 'md:col-start-8', label: 'Dejar 7 espacios' },
        { value: 'md:col-start-9', label: 'Dejar 8 espacios' },
        { value: 'md:col-start-10', label: 'Dejar 9 espacios' },
        { value: 'md:col-start-11', label: 'Dejar 10 espacios' },
      ],
    };

    static get drawerFields() {
      return [this.FIELD_TITLE, this.FIELD_FUNCTION_PATH, this.FIELD_WIDTH, this.FIELD_HEIGHT, this.FIELD_START_COL];
    }

    static _parseSpan(widthClass) {
      const m = /md:col-span-(\d+)/.exec(widthClass);
      return m ? parseInt(m[1], 10) : 6;
    }

    static getGhostSpan() {
      return BaseWidget._parseSpan(this.defaults.width);
    }

    _ghostSpanFromWidth() {
      return BaseWidget._parseSpan(this.width);
    }

    static escapeHTML(str) {
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    }

    static DOWNLOAD_ICON_SVG = `<svg viewBox="0 0 14 14" class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M7 1.5v8M7 9.5 4 6.5M7 9.5l3-3M2 11.5v1a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-1"/>
    </svg>`;

    downloadButtonHTML(title = 'Descargar CSV') {
      return `<button class="download-csv-btn text-ink/40 hover:text-moss-600 transition cursor-pointer p-0.5" title="${title}">
        ${BaseWidget.DOWNLOAD_ICON_SVG}
      </button>`;
    }

    _filenameSlug(fallback) {
      return (this.title || fallback).trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || fallback;
    }

    downloadRowsAsCSV(headers, rows, filename) {
      const escapeCell = (v) => {
        const s = v === null || v === undefined ? '' : String(v);
        return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      };
      const csv = [headers, ...rows].map(r => r.map(escapeCell).join(',')).join('\r\n');
      const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
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
      this.startCol = raw.startCol
        ? (raw.startCol.startsWith('md:') ? raw.startCol : 'md:' + raw.startCol)
        : '';
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
      el.className = `col-span-12 ${this.width}${this.startCol ? ' ' + this.startCol : ''} bg-white border border-line rounded-xl shadow-sm p-4 flex flex-col justify-between relative group`;
      el.style.height = this.height + 'px';
      el.style.setProperty('--ghost-span', this._ghostSpanFromWidth());
      el.dataset.widgetId = this.id;
      el.dataset.type = this.chart_type;
      el.innerHTML = `
        ${BaseWidget.dragHandleHTML()}
        <div class="flex justify-between items-center border-line pb-2 mb-2 select-none">
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
      this._attachFiltersListener();
      const container = this.getContentContainer();
      if (container) {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => this.renderContent(container));
        });
      }
      return this.el;
    }

    buildReadOnlyElement() {
      const el = document.createElement('div');
      el.className = `col-span-12 ${this.width}${this.startCol ? ' ' + this.startCol : ''} bg-white border border-line rounded-xl shadow-sm p-4 flex flex-col justify-between relative`;
      el.style.height = this.height + 'px';
      el.dataset.widgetId = this.id;
      el.dataset.type = this.chart_type;
      const titleHTML = this.title
        ? `<div class="flex items-center border-line pb-2 mb-2"><span class="text-[10px] font-bold uppercase tracking-wider text-ink/40">${BaseWidget.escapeHTML(this.title)}</span></div>`
        : '';
      el.innerHTML = `${titleHTML}<div id="chart-${this.id}" class="flex-1 w-full min-h-0"></div>${this.loaderOverlayHTML()}
        <div class="actions-slot absolute top-2 right-2 z-30 flex items-center gap-1"></div>`;
      return el;
    }

    mountReadOnly() {
      this.el = this.buildReadOnlyElement();
      this._attachFiltersListener();
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

      Array.from(this.el.classList).filter(c => c.startsWith('col-start-') || c.startsWith('md:col-start-') || c.startsWith('md:col-span-')).forEach(c => this.el.classList.remove(c));
      this.el.classList.add(this.width);
      if (this.startCol) this.el.classList.add(this.startCol);
      this.el.style.height = this.height + 'px';
      this.el.style.setProperty('--ghost-span', this._ghostSpanFromWidth());

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

    renderError(message) {
      const container = this.getContentContainer();
      if (!container) return;
      if (this._chart) {
        this._chart.destroy();
        this._chart = null;
      }
      container.innerHTML = `
        <div class="h-full w-full flex items-center justify-center text-center px-3">
          <span class="text-xs text-red-600">${BaseWidget.escapeHTML(message || 'Error al cargar los datos')}</span>
        </div>
      `;
    }

    async fetchAndRender() {
      if (this.id < 0) return;
      if (!this.functionPath) {
        const container = this.getContentContainer();
        if (container) this.renderContent(container);
        return;
      }
      this.setLoading(true);
      try {
        const r = await fetch(`/api/widget/${this.id}/data/`);
        const data = await r.json().catch(() => null);
        if (!r.ok) {
          this.renderError(data && data.error ? data.error : `Error ${r.status} al cargar los datos`);
          return;
        }
        const container = this.getContentContainer();
        if (container) this.renderContent(container, data);
      } catch (e) {
        this.renderError('No se pudo conectar con el servidor');
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
        this.destroy();
        el.remove();
      });

      const resizeHandle = el.querySelector('.resize-handle');
      if (resizeHandle) resizeHandle.addEventListener('mousedown', (e) => this._onResizeStart(e));
    }

    _attachFiltersListener() {
      this._onFiltersChanged = () => this.fetchAndRender();
      window.addEventListener('dashboard:filters-changed', this._onFiltersChanged);
    }

    destroy() {
      window.removeEventListener('dashboard:filters-changed', this._onFiltersChanged);
      if (this._chart) {
        this._chart.destroy();
        this._chart = null;
      }
    }

    _onResizeStart(e) {
      e.preventDefault();
      e.stopPropagation();

      const el = this.el;
      const minHeight = this.constructor.minHeight;
      const startY = e.clientY;
      const startHeight = el.offsetHeight;

      const onMouseMove = (ev) => {
        const newHeight = Math.max(minHeight, startHeight + (ev.clientY - startY));
        el.style.height = newHeight + 'px';
        window.dispatchEvent(new Event('resize'));
      };

      const onMouseUp = () => {
        this.height = el.offsetHeight;
        this._dirty = true;
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
      };

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    }
  }

  window.BaseWidget = BaseWidget;
})();
