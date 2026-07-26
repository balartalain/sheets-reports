(function () {
  document.addEventListener('alpine:init', () => {
    const store = Alpine.store('dashboard');

    store.filters = {};

    store.initFiltersFromURL = function () {
      const params = new URLSearchParams(window.location.search);
      for (const [key, value] of params) {
        if (key.startsWith('filtro_')) {
          this.filters[key.slice(7)] = value || '';
        }
      }
    };

    store.setFilter = function (field, value) {
      if (value) {
        this.filters = { ...this.filters, [field]: value };
      } else {
        const f = { ...this.filters };
        delete f[field];
        this.filters = f;
      }
      this._syncFiltersToURL();
      window.dispatchEvent(new CustomEvent('dashboard:filters-changed'));
    };

    store.clearFilter = function (field) {
      const f = { ...this.filters };
      delete f[field];
      this.filters = f;
      this._syncFiltersToURL();
      window.dispatchEvent(new CustomEvent('dashboard:filters-changed'));
    };

    store._syncFiltersToURL = function () {
      const url = new URL(window.location);
      const keysToDelete = [...url.searchParams.keys()].filter(k => k.startsWith('filtro_'));
      for (const k of keysToDelete) url.searchParams.delete(k);
      for (const [field, value] of Object.entries(this.filters)) {
        if (value) url.searchParams.set('filtro_' + field, value);
      }
      history.replaceState({}, '', url);
    };

    store.getFilterQueryString = function () {
      const params = new URLSearchParams();
      for (const [field, value] of Object.entries(this.filters)) {
        if (value) params.set('filtro_' + field, value);
      }
      return params.toString();
    };

    store.initFiltersFromURL();
  });
})();
