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
  function toast(message, link) {
    const el = $('#toast'); el.textContent = message;
    if (link) { const a = document.createElement('a'); a.href = link.href; a.textContent = link.text; el.append(a); }
    el.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => el.hidden = true, link ? 9000 : 5000);
  }
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
  // Skill map: area tabs → general topics (details) → niche skills. Each tick saves immediately.
  const checklist = $('[data-checklist]');
  if (checklist) {
    $('[data-checklist-save]', checklist).hidden = true;
    const csrf = $('[name=csrfmiddlewaretoken]', checklist).value;
    const tabs = $('[data-sector-tabs]', checklist), hint = $('[data-sector-hint]', checklist);
    const panels = $$('[data-sector]', checklist);
    tabs.hidden = false; checklist.classList.add('js-tabs');
    const select = key => {
      $$('[data-tab]', tabs).forEach(t => t.setAttribute('aria-selected', String(t.dataset.tab === key)));
      panels.forEach(p => { p.hidden = p.dataset.sector !== key; });
      hint.hidden = Boolean(key);
      try { if (key) sessionStorage.setItem('ll-sector', key); else sessionStorage.removeItem('ll-sector'); } catch { /* storage blocked */ }
    };
    tabs.addEventListener('click', e => {
      const tab = e.target.closest('[data-tab]'); if (!tab) return;
      select(tab.getAttribute('aria-selected') === 'true' ? '' : tab.dataset.tab);
    });
    let remembered = ''; try { remembered = sessionStorage.getItem('ll-sector') || ''; } catch { /* ignore */ }
    select(panels.some(p => p.dataset.sector === remembered) ? remembered : '');

    const recount = () => {
      $$('[data-topic]', checklist).forEach(t => {
        const skills = $$('[data-skill]', t), known = skills.filter(s => s.checked).length;
        $('[data-topic-count]', t).textContent = known;
        t.classList.toggle('complete', known === skills.length);
      });
      panels.forEach(p => {
        const skills = $$('[data-skill]', p), known = skills.filter(s => s.checked).length;
        const tab = $(`[data-tab="${p.dataset.sector}"]`, tabs);
        $('[data-sector-count]', tab).textContent = known;
        $('[data-tab-bar]', tab).style.width = `${Math.round(known / skills.length * 100)}%`;
      });
      const all = $$('[data-skill]', checklist), known = all.filter(s => s.checked).length;
      $('[data-checklist-count]').textContent = known;
      $('[data-checklist-bar]').style.width = `${Math.round(known / all.length * 100)}%`;
    };
    // "I know all of X" shows every skill inside as covered; unticking restores each skill's own state.
    const cover = general => {
      $$('[data-skill]', general.closest('[data-topic]')).forEach(s => {
        s.disabled = general.checked; s.checked = general.checked || s.dataset.own === '1';
      });
    };
    const showProgress = (p, levelUp) => {
      $('[data-level]').textContent = p.level;
      $('[data-motivation]').textContent = p.message;
      const next = $('[data-next]'); if (next) next.textContent = p.next_level ? `${p.to_next} more to reach ${p.next_level}.` : '';
      $('[data-checklist-count]').textContent = p.count;
      if (levelUp) { toast(`Level up: ${p.level}! ${p.message}`); $('#toast').classList.add('celebrate'); }
    };
    checklist.addEventListener('change', async e => {
      const box = e.target; if (box.type !== 'checkbox') return;
      if (box.matches('[data-general]')) cover(box); else box.dataset.own = box.checked ? '1' : '0';
      const label = box.closest('label'); label.setAttribute('aria-busy', 'true'); recount();
      const body = new FormData(); body.append('csrfmiddlewaretoken', csrf); body.append('topic', box.value); body.append('known', box.checked ? '1' : '0');
      try {
        const response = await fetch(checklist.action, {method: 'POST', body, headers: {Accept: 'application/json'}});
        if (!response.ok || response.redirected) throw new Error('save failed');
        const data = await response.json();
        $('#toast').classList.remove('celebrate');
        if (!data.level_up) toast(data.known ? `Got it: ${data.name}. ${data.progress.count} skills known.` : `${data.name} is back on the learning list.`);
        showProgress(data.progress, data.level_up);
      } catch {
        box.checked = !box.checked;
        if (box.matches('[data-general]')) cover(box); else box.dataset.own = box.checked ? '1' : '0';
        recount(); toast('Could not save that change. Check your connection and try again.');
      } finally { label.removeAttribute('aria-busy'); }
    });
    recount();
  }
  // Personalize page: live preview. Elements declare when they show, e.g. data-when="terminal:visual depth:!brief".
  const personalize = $('[data-personalize]');
  if (personalize) {
    const state = () => ({
      depth: $('[name=explanation_depth]:checked', personalize)?.value || 'standard',
      diagrams: $('[name=show_diagrams]', personalize).checked ? 'on' : 'off',
      analogies: $('[name=use_analogies]', personalize).checked ? 'on' : 'off',
      terminal: $('[name=terminal_detail]:checked', personalize)?.value || 'compact',
    });
    const update = () => {
      const s = state();
      $$('[data-when]').forEach(el => {
        el.hidden = !el.dataset.when.split(/\s+/).every(rule => {
          const [key, raw] = rule.split(':'), negate = raw.startsWith('!'), value = negate ? raw.slice(1) : raw;
          return (s[key] === value) !== negate;
        });
      });
    };
    personalize.addEventListener('change', update);
    update();
  }
  // Live updates: new cards from the plugin appear while a member page is open.
  if (path.startsWith('/app/') && !path.startsWith('/app/first-login')) {
    let latest = null, timer;
    const poll = async () => {
      try {
        const response = await fetch('/app/cards/latest.json', {headers: {Accept: 'application/json'}});
        if (!response.ok || response.redirected) return;
        const data = await response.json();
        if (latest !== null && data.latest_id > latest) toast(`New card: ${data.concept}.`, {href: data.url, text: 'Open it'});
        latest = data.latest_id;
        $$('[data-unread-count]').forEach(el => { el.textContent = data.unread; });
      } catch { /* offline: try again on the next tick */ }
    };
    const schedule = () => { clearInterval(timer); if (!document.hidden) { poll(); timer = setInterval(poll, 6000); } };
    document.addEventListener('visibilitychange', schedule);
    schedule();
  }
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
