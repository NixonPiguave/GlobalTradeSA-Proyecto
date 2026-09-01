/*
 * auth.js — Sesión del panel admin (JWT en localStorage) y guarda global.
 * Debe cargarse ANTES que app.js. Añade Authorization a todas las llamadas /api
 * y redirige a login ante 401.
 */
(function () {
  const TOKEN_KEY = 'globtrade-admin-token';
  const USER_KEY = 'globtrade-admin-user';

  window.adminAuth = {
    token() { return localStorage.getItem(TOKEN_KEY); },
    user() {
      try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); }
      catch { return null; }
    },
    save(token, user) {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user || null));
    },
    clear() {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    },
    logout() {
      this.clear();
      window.location.replace('/pages/login.html');
    },
  };

  const enLogin = window.location.pathname.indexOf('/pages/login.html') !== -1;
  if (!enLogin && !window.adminAuth.token()) {
    window.location.replace('/pages/login.html');
    return;
  }

  const fetchOriginal = window.fetch.bind(window);
  window.fetch = function (input, init) {
    init = init || {};
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const esApi = url.indexOf('/api') === 0 || url.indexOf(window.location.origin + '/api') === 0;
    const esLogin = url.indexOf('/api/auth/login') !== -1;
    if (esApi && !esLogin) {
      const token = window.adminAuth.token();
      if (token) {
        const headers = new Headers(init.headers || {});
        if (!headers.has('Authorization')) headers.set('Authorization', 'Bearer ' + token);
        init.headers = headers;
      }
    }
    return fetchOriginal(input, init).then(function (res) {
      if (res.status === 401 && esApi && !esLogin && !enLogin) {
        window.adminAuth.clear();
        window.location.replace('/pages/login.html');
      }
      return res;
    });
  };

  document.addEventListener('DOMContentLoaded', function () {
    const chip = document.getElementById('session-chip');
    const user = window.adminAuth.user();
    if (chip && user) {
      chip.textContent = user.email + ' · ' + user.rol;
      chip.hidden = false;
    }
    const btn = document.getElementById('logout-btn');
    if (btn) btn.addEventListener('click', function () { window.adminAuth.logout(); });
  });
})();
