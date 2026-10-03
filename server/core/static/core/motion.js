/* A progressive motion layer: no content hiding, external libraries, or continuous JS loop. */
(() => {
  'use strict';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
  const controls = [...document.querySelectorAll('[data-motion-toggle]')];
  const activeAnimations = new Set();
  const seen = new WeakSet();
  const storageKey = 'learnloop.motion';
  let preferred = true;
  try { preferred = localStorage.getItem(storageKey) !== 'off'; } catch { /* Private storage may be unavailable. */ }
  let enabled = false;
  let observer;
  let frame = 0;
  let pointerTarget;
  let point;
  const surfaces = [...document.querySelectorAll('.learning-card, .feature-grid .panel, .hero-preview, .auth-form')];
  surfaces.forEach(surface => surface.setAttribute('data-spotlight', ''));

  function animate(element, keyframes, options) {
    if (!enabled || document.hidden || !element.animate) return;
    const animation = element.animate(keyframes, options);
    activeAnimations.add(animation);
    const release = () => activeAnimations.delete(animation);
    animation.addEventListener('finish', release, {once: true});
    animation.addEventListener('cancel', release, {once: true});
  }

  function reveal(element, delay) {
    if (seen.has(element)) return;
    seen.add(element);
    // Keep the real content and final values in the DOM at all times.
    animate(element, [
      {opacity: .35, transform: 'translateY(14px)'},
      {opacity: 1, transform: 'translateY(0)'}
    ], {duration: 650, delay, easing: 'cubic-bezier(.16,1,.3,1)', fill: 'backwards'});
    element.querySelectorAll('.activity-bar, .snapshot-track>span, .meter span').forEach((bar, index) => {
      const horizontal = bar.closest('.meter');
      animate(bar, [{transform: horizontal ? 'scaleX(0)' : 'scaleY(0)'}, {transform: 'scale(1)'}], {
        duration: 800, delay: delay + Math.min(index * 16, 250), easing: 'cubic-bezier(.16,1,.3,1)'
      });
    });
  }

  function observe() {
    observer?.disconnect();
    if (!enabled || !('IntersectionObserver' in window)) return;
    observer = new IntersectionObserver(entries => {
      let order = 0;
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        reveal(entry.target, Math.min(order++ * 65, 195));
        observer.unobserve(entry.target);
      });
    }, {threshold: .08});
    document.querySelectorAll('.page-heading, .hero-copy, .auth-story, main .panel, .team-banner, .landing-divider').forEach(el => observer.observe(el));
  }

  function resetPointer() {
    cancelAnimationFrame(frame);
    frame = 0;
    if (!pointerTarget) return;
    ['--pointer-x', '--pointer-y', '--tilt-x', '--tilt-y'].forEach(property => pointerTarget.style.removeProperty(property));
    pointerTarget = null;
  }

  function sync() {
    enabled = preferred && !reduced.matches;
    document.body.classList.toggle('motion-enabled', enabled);
    controls.forEach(button => {
      button.hidden = false;
      button.setAttribute('aria-pressed', String(enabled));
      button.disabled = reduced.matches;
      button.title = reduced.matches ? 'Motion follows your system’s reduced-motion preference' : (enabled ? 'Pause decorative motion' : 'Enable decorative motion');
    });
    activeAnimations.forEach(animation => animation.cancel());
    activeAnimations.clear();
    resetPointer();
    observe();
  }
  controls.forEach(button => button.addEventListener('click', () => {
    preferred = !preferred;
    try { localStorage.setItem(storageKey, preferred ? 'on' : 'off'); } catch { /* Preference still works for this page. */ }
    sync();
  }));
  reduced.addEventListener('change', sync);
  finePointer.addEventListener('change', resetPointer);
  window.addEventListener('storage', event => { if (event.key === storageKey) { preferred = event.newValue !== 'off'; sync(); } });

  // Coalesce pointer events into one layout read and style update per frame.
  document.addEventListener('pointermove', event => {
    if (!enabled || !finePointer.matches || document.hidden) return;
    const target = event.target.closest('[data-spotlight], .hero-art');
    if (target !== pointerTarget) { resetPointer(); pointerTarget = target; }
    if (!target) return;
    point = {x: event.clientX, y: event.clientY};
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      if (!pointerTarget) return;
      const rect = pointerTarget.getBoundingClientRect();
      const x = Math.max(0, Math.min(1, (point.x - rect.left) / rect.width));
      const y = Math.max(0, Math.min(1, (point.y - rect.top) / rect.height));
      pointerTarget.style.setProperty('--pointer-x', `${x * 100}%`);
      pointerTarget.style.setProperty('--pointer-y', `${y * 100}%`);
      if (pointerTarget.matches('.hero-art')) {
        pointerTarget.style.setProperty('--tilt-x', `${(0.5 - y) * 4}deg`);
        pointerTarget.style.setProperty('--tilt-y', `${(x - 0.5) * 4}deg`);
      }
    });
  }, {passive: true});
  document.documentElement.addEventListener('pointerleave', resetPointer);
  window.addEventListener('blur', resetPointer);
  document.addEventListener('visibilitychange', () => {
    document.body.classList.toggle('effects-suspended', document.hidden);
    if (document.hidden) resetPointer();
    activeAnimations.forEach(animation => document.hidden ? animation.pause() : animation.play());
  });
  // Keyboard focus must never wait for an entrance animation to finish.
  document.addEventListener('focusin', () => {
    // Finishing on pointer-down can move a link before pointer-up and swallow its click.
    if (!document.activeElement?.matches(':focus-visible')) return;
    activeAnimations.forEach(animation => { if (animation.effect?.target?.contains(document.activeElement)) animation.finish(); });
  });
  sync();
})();
