(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const path = location.pathname;
  let active;
  $$('[data-nav]').forEach(link => {
    const href = new URL(link.href).pathname;
    const match = path === href || (!['/app/', '/manage/'].includes(href) && path.startsWith(href));
    if (match) { link.setAttribute('aria-current', 'page'); active = link; }
  });
  if ($('#page-label')) $('#page-label').textContent = active ? active.textContent.trim().slice(1).trim() : 'Workspace';
  if (document.title === 'LearnLoop · Your learning workspace') {
    const heading = $('main h1, main h2');
    if (heading) document.title = `${heading.textContent.trim()} · LearnLoop`;
  }
  $$('.subnav a').forEach(a => { if (path === new URL(a.href).pathname) a.setAttribute('aria-current', 'page'); });
  const toggle = $('.mobile-toggle'), sidebar = $('#sidebar'), backdrop = $('.nav-backdrop');
  const narrow = matchMedia('(max-width: 850px)');
  function navigation(open, focus = true) {
    document.body.classList.toggle('nav-open', open);
    if (!sidebar) return;
    toggle.setAttribute('aria-expanded', String(open));
    sidebar.inert = narrow.matches && !open;
    backdrop.hidden = !open;
    if (open) $('.brand', sidebar).focus();
    else if (focus) toggle.focus();
  }
  if (toggle) {
    toggle.addEventListener('click', () => navigation(!document.body.classList.contains('nav-open')));
    backdrop.addEventListener('click', () => navigation(false));
    narrow.addEventListener('change', () => navigation(false, false));
    navigation(false, false);
  }
  const dialog = $('#command-palette');
  let searchOpener;
  function openSearch(event) {
    if (!dialog || dialog.open) return;
    searchOpener = event?.currentTarget || document.activeElement;
    if (document.body.classList.contains('nav-open')) navigation(false, false);
    dialog.showModal(); $('#global-search').focus();
  }
  $$('[data-open-search]').forEach(b => b.addEventListener('click', openSearch));
  $('[data-close-search]')?.addEventListener('click', () => dialog.close());
  dialog?.addEventListener('close', () => { if (searchOpener && !searchOpener.closest('[inert]')) searchOpener.focus(); else toggle?.focus(); });
  dialog?.addEventListener('click', e => { if (e.target === dialog) { const r = dialog.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close(); } });
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openSearch(); }
    if (e.key === 'Escape') { if (document.body.classList.contains('nav-open')) navigation(false); $$('.profile-menu[open]').forEach(d => d.open = false); }
    if (e.key === 'Tab' && document.body.classList.contains('nav-open') && !dialog?.open) {
      const focusable = $$('a, button, summary', sidebar).filter(el => el.getClientRects().length);
      const first = focusable[0], last = focusable.at(-1);
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  $$('[data-dismiss]').forEach(b => b.addEventListener('click', () => b.closest('li').remove()));
  let toastTimer;
  function toast(message) { const el = $('#toast'); el.textContent = message; el.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => el.hidden = true, 5000); }
  $$('[data-copy]').forEach(b => b.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(document.getElementById(b.dataset.copy).textContent.trim()); toast('Copied to clipboard.'); }
    catch { toast('Clipboard unavailable. Select the text and copy it manually.'); }
  }));
  // Never disable the submitter: its name/value is part of the existing POST contract.
  $$('form[method="post"]').forEach(form => form.addEventListener('submit', e => {
    if (form.dataset.submitting) { e.preventDefault(); return; }
    form.dataset.submitting = 'true'; form.setAttribute('aria-busy', 'true');
    if (e.submitter) { e.submitter.dataset.originalLabel = e.submitter.textContent; e.submitter.classList.add('busy-label'); e.submitter.textContent = e.submitter.dataset.loading || 'Working…'; }
  }));
  window.addEventListener('pageshow', () => {
    $$('form[data-submitting]').forEach(f => { delete f.dataset.submitting; f.removeAttribute('aria-busy'); });
    $$('[data-original-label]').forEach(b => { b.textContent = b.dataset.originalLabel; b.classList.remove('busy-label'); });
  });
  const test = $('#test');
  test?.addEventListener('click', async () => {
    const status = $('#status'); test.disabled = true; status.textContent = 'Checking connection…'; status.className = 'busy-label muted';
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(test.dataset.url, {signal: controller.signal, headers: {Accept: 'application/json'}});
      if (!response.ok || response.redirected) throw new Error('Request failed');
      const data = await response.json();
      status.textContent = data.connected ? `Connected · Last ping ${new Date(data.last_ping).toLocaleTimeString()}` : 'No recent ping. Start a new Claude Code session, then try again.';
      status.className = data.connected ? 'chip known' : 'muted';
    } catch { status.textContent = 'Could not check the connection. Check your network or sign in again, then retry.'; status.className = 'errorlist'; }
    finally { clearTimeout(timeout); test.disabled = false; }
  });
})();
