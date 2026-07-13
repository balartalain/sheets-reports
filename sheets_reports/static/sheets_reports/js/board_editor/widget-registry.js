(function () {
  class WidgetRegistry {
    static _types = new Map();

    static register(WidgetClass) {
      const type = WidgetClass.type;
      if (!type) throw new Error('WidgetRegistry.register: la clase debe definir static type');
      if (this._types.has(type)) console.warn(`WidgetRegistry: sobrescribiendo el tipo "${type}"`);
      this._types.set(type, WidgetClass);
    }

    static has(type) {
      return this._types.has(type);
    }

    static get(type) {
      const WidgetClass = this._types.get(type);
      if (!WidgetClass) throw new Error(`WidgetRegistry: tipo de widget desconocido "${type}"`);
      return WidgetClass;
    }

    static getAll() {
      return [...this._types.values()];
    }

    static getTypes() {
      return [...this._types.keys()];
    }

    static getPaletteEntries() {
      return this.getAll().map((WidgetClass) => ({
        type: WidgetClass.type,
        ghostSpan: WidgetClass.getGhostSpan(),
        ...WidgetClass.palette,
      }));
    }

    static create(type, raw) {
      return new (this.get(type))(raw);
    }
  }

  window.WidgetRegistry = WidgetRegistry;
})();
