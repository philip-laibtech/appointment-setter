(function () {
  var sidebar = document.getElementById('sidebar');
  var pin     = document.getElementById('sbPin');
  var menuBtn = document.getElementById('sbMenuBtn');
  var overlay = document.getElementById('sbOverlay');
  var body    = document.body;
  var KEY     = 'sb_c';
  var BP      = 768;

  if (window.innerWidth > BP && localStorage.getItem(KEY) === '1') {
    sidebar.classList.add('is-collapsed');
    body.classList.add('sb-collapsed');
  }

  pin.addEventListener('click', function () {
    var c = sidebar.classList.toggle('is-collapsed');
    body.classList.toggle('sb-collapsed', c);
    localStorage.setItem(KEY, c ? '1' : '0');
  });

  menuBtn.addEventListener('click', function () {
    sidebar.classList.add('mob-open');
    overlay.classList.add('is-open');
  });

  overlay.addEventListener('click', function () {
    sidebar.classList.remove('mob-open');
    overlay.classList.remove('is-open');
  });

  window.addEventListener('resize', function () {
    if (window.innerWidth > BP) {
      sidebar.classList.remove('mob-open');
      overlay.classList.remove('is-open');
    }
  });
})();

(function () {
  var inflight = null;

  function swapStyles(newDoc) {
    Array.from(document.head.querySelectorAll('style')).slice(1).forEach(function (s) { s.remove(); });
    Array.from(newDoc.head.querySelectorAll('style')).slice(1).forEach(function (s) {
      document.head.appendChild(s.cloneNode(true));
    });
  }

  function runScripts(container) {
    Array.from(container.querySelectorAll('script')).forEach(function (old) {
      var fresh = document.createElement('script');
      Array.from(old.attributes).forEach(function (a) { fresh.setAttribute(a.name, a.value); });
      fresh.textContent = old.textContent;
      old.parentNode.replaceChild(fresh, old);
    });
  }

  function setActive(pathname) {
    document.querySelectorAll('.nav-link').forEach(function (link) {
      var lp = new URL(link.href, location.origin).pathname;
      link.classList.toggle('is-active', pathname === lp || (lp.length > 1 && pathname.startsWith(lp)));
    });
  }

  function navigate(url, push) {
    if (inflight) { inflight.abort(); }
    inflight = new AbortController();
    fetch(url, { signal: inflight.signal })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        var newDoc = new DOMParser().parseFromString(html, 'text/html');
        swapStyles(newDoc);
        var newMain = newDoc.querySelector('main');
        var curMain = document.querySelector('main');
        if (newMain && curMain) {
          curMain.innerHTML = newMain.innerHTML;
          runScripts(curMain);
        }
        var nt = newDoc.querySelector('.topbar-title');
        var ct = document.querySelector('.topbar-title');
        if (nt && ct) ct.innerHTML = nt.innerHTML;
        document.title = newDoc.title;
        if (push !== false) history.pushState({ spaUrl: url }, '', url);
        setActive(new URL(url, location.origin).pathname);
      })
      .catch(function (e) { if (e.name !== 'AbortError') location.href = url; });
  }

  function handleNavClick(e) {
    var link = e.target.closest('a.nav-link');
    if (!link || new URL(link.href, location.origin).origin !== location.origin) return;
    e.preventDefault();
    navigate(link.href, true);
  }

  document.querySelector('.sb-nav').addEventListener('click', handleNavClick);
  document.querySelector('.sb-footer').addEventListener('click', handleNavClick);

  window.addEventListener('popstate', function (e) {
    navigate(e.state && e.state.spaUrl ? e.state.spaUrl : location.href, false);
  });

  history.replaceState({ spaUrl: location.href }, '', location.href);
})();
