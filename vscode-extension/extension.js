// LearnLoop for VS Code: shows the cards the LearnLoop server writes for you, next to the code they explain.
// Plain JavaScript, no dependencies, no build step. Talks to the same API (and token) as the Claude Code plugin.
'use strict';

const vscode = require('vscode');
const path = require('path');

const TOKEN_KEY = 'learnloop.token';
const LAST_SEEN_KEY = 'learnloop.lastSeenId';

class ApiError extends Error {
  constructor(kind, message) { super(message); this.kind = kind; }
}

class Api {
  constructor(context) { this.context = context; }

  get baseUrl() {
    return (vscode.workspace.getConfiguration('learnloop').get('serverUrl') || '').trim().replace(/\/+$/, '');
  }

  token() { return this.context.secrets.get(TOKEN_KEY); }

  async request(method, urlPath, body) {
    const token = await this.token();
    if (!token) throw new ApiError('not-configured', 'Connect LearnLoop first.');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(this.baseUrl + urlPath, {
        method,
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'User-Agent': 'learnloop-vscode/0.1.0' },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      if (response.status === 401) throw new ApiError('unauthorized', 'LearnLoop rejected your token. Get a new one on the Setup page.');
      if (!response.ok) throw new ApiError('http', `LearnLoop answered with HTTP ${response.status}.`);
      return await response.json();
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('offline', `Can't reach LearnLoop at ${this.baseUrl}.`);
    } finally {
      clearTimeout(timer);
    }
  }

  ping() { return this.request('GET', '/api/v1/ping'); }
  cards() { return this.request('GET', '/api/v1/cards?limit=40'); }
  act(id, action) { return this.request('POST', `/api/v1/cards/${id}/action`, { action }); }
}

// ---------------------------------------------------------------------------
// Sidebar: list of cards
// ---------------------------------------------------------------------------
class CardsProvider {
  constructor() {
    this.cards = [];
    this.emitter = new vscode.EventEmitter();
    this.onDidChangeTreeData = this.emitter.event;
  }

  set(cards) { this.cards = cards; this.emitter.fire(); }

  getTreeItem(card) {
    const item = new vscode.TreeItem(card.concept, vscode.TreeItemCollapsibleState.None);
    item.id = String(card.id);
    item.description = card.file ? path.basename(card.file) : card.category;
    item.tooltip = new vscode.MarkdownString(`**${md(card.concept)}**\n\n${md(card.summary)}\n\n_${md(card.why_here || '')}_`);
    if (card.status === 'known') item.iconPath = new vscode.ThemeIcon('pass', new vscode.ThemeColor('testing.iconPassed'));
    else if (card.status === 'muted') item.iconPath = new vscode.ThemeIcon('circle-slash');
    else if (!card.read) item.iconPath = new vscode.ThemeIcon('lightbulb', new vscode.ThemeColor('charts.yellow'));
    else item.iconPath = new vscode.ThemeIcon('lightbulb');
    item.contextValue = card.status === 'known' || card.status === 'muted' ? 'card-done' : 'card';
    item.command = { command: 'learnloop.openCard', title: 'Open card', arguments: [card] };
    return item;
  }

  getChildren(element) { return element ? [] : this.cards; }
}

// ---------------------------------------------------------------------------
// CodeLens: "💡 LearnLoop: <concept>" above the code a card is about
// ---------------------------------------------------------------------------
class CardLens {
  constructor(provider) {
    this.provider = provider;
    this.emitter = new vscode.EventEmitter();
    this.onDidChangeCodeLenses = this.emitter.event;
  }

  refresh() { this.emitter.fire(); }

  provideCodeLenses(document) {
    if (!vscode.workspace.getConfiguration('learnloop').get('codeLens')) return [];
    const rel = vscode.workspace.asRelativePath(document.uri, false).replace(/\\/g, '/');
    const text = document.getText();
    const lenses = [];
    for (const card of this.provider.cards) {
      if (!card.file || card.status === 'known' || card.status === 'muted' || !sameFile(card.file, rel)) continue;
      const line = lineOfSnippet(text, card.snippet);
      const range = new vscode.Range(line, 0, line, 0);
      lenses.push(new vscode.CodeLens(range, { title: `💡 LearnLoop: ${card.concept}`, command: 'learnloop.openCard', arguments: [card] }));
    }
    return lenses;
  }
}

function sameFile(cardFile, rel) {
  const a = cardFile.replace(/\\/g, '/').replace(/^\.\//, '');
  return a === rel || rel.endsWith('/' + a) || a.endsWith('/' + rel);
}

function lineOfSnippet(text, snippet) {
  const first = (snippet || '').split('\n').map(l => l.trim()).find(l => l.length > 3);
  if (!first) return 0;
  const lines = text.split('\n');
  const index = lines.findIndex(l => l.includes(first));
  return index >= 0 ? index : 0;
}

// ---------------------------------------------------------------------------
// Card detail: one reusable webview panel
// ---------------------------------------------------------------------------
let panel;

function showCard(card, controller) {
  if (!panel) {
    panel = vscode.window.createWebviewPanel('learnloop.card', 'LearnLoop', { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true }, { enableScripts: true });
    panel.onDidDispose(() => { panel = undefined; });
    panel.webview.onDidReceiveMessage(msg => controller.handleCardMessage(msg));
  }
  panel.title = `💡 ${card.concept}`;
  panel.webview.html = cardHtml(card, panel.webview);
  panel.reveal(vscode.ViewColumn.Beside, true);
}

function cardHtml(card, webview) {
  const nonce = Math.random().toString(36).slice(2) + Date.now().toString(36);
  // Mermaid is loaded from jsDelivr to draw the diagram; offline, the text flow below it still explains the steps.
  const csp = `default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; img-src data:; font-src data:; script-src 'nonce-${nonce}' https://cdn.jsdelivr.net;`;
  const flow = (card.flow || []).map(step => `<li>${esc(step)}</li>`).join('');
  const done = card.status === 'known' || card.status === 'muted';
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font-family:var(--vscode-font-family);color:var(--vscode-foreground);padding:8px 16px 24px;line-height:1.55;max-width:760px}
.eyebrow{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--vscode-descriptionForeground)}
h1{font-size:20px;margin:4px 0 12px}
.why{border-left:3px solid var(--vscode-textLink-foreground);padding:6px 12px;background:var(--vscode-textBlockQuote-background)}
pre{background:var(--vscode-textCodeBlock-background);padding:12px;border-radius:6px;overflow:auto;font-family:var(--vscode-editor-font-family);font-size:var(--vscode-editor-font-size)}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}
button{background:var(--vscode-button-background);color:var(--vscode-button-foreground);border:0;padding:6px 14px;border-radius:3px;cursor:pointer;font:inherit}
button.secondary{background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground)}
button:focus-visible{outline:1px solid var(--vscode-focusBorder);outline-offset:2px}
a{color:var(--vscode-textLink-foreground)}
.status{color:var(--vscode-testing-iconPassed)}
.diagram{border:1px solid var(--vscode-panel-border);border-radius:6px;padding:12px;margin:12px 0;overflow:auto;text-align:center}
.diagram svg{max-width:100%;height:auto}
.flow{margin:6px 0 0;padding-left:18px;color:var(--vscode-descriptionForeground);text-align:left}
.callout{border-left:3px solid var(--vscode-textLink-foreground);padding:6px 12px;margin:10px 0}
.callout.warn{border-left-color:var(--vscode-editorWarning-foreground)}
</style></head><body>
<div class="eyebrow">${esc(card.category || 'concept')}${card.file ? ' · ' + esc(card.file) : ''}</div>
<h1>${esc(card.concept)}</h1>
<p>${esc(card.summary)}</p>
${card.why_here ? `<p class="why"><b>Why it's here:</b> ${esc(card.why_here)}</p>` : ''}
${card.diagram ? `<div class="diagram"><div id="diagram"></div><ol class="flow" id="flow">${flow}</ol></div>` : ''}
${card.snippet ? `<pre><code>${esc(card.snippet)}</code></pre>` : ''}
${card.pitfall ? `<p class="callout warn"><b>⚠ Watch out:</b> ${esc(card.pitfall)}</p>` : ''}
${card.analogy ? `<p class="callout"><b>Think of it like:</b> ${esc(card.analogy)}</p>` : ''}
${card.doc_url ? `<p>Official docs: <a href="${esc(card.doc_url)}">${esc(card.doc_url)}</a></p>` : ''}
${done ? `<p class="status">✓ You marked this as ${esc(card.status)}. LearnLoop won't explain it again.</p>` : ''}
<div class="actions">
${done ? '' : '<button data-action="known">I know this</button><button class="secondary" data-action="mute">Don\'t explain again</button>'}
${card.file ? '<button class="secondary" data-action="openFile">Go to code</button>' : ''}
<button class="secondary" data-action="openWeb">Open on the web</button>
</div>
${card.diagram ? `<script nonce="${nonce}" src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script nonce="${nonce}">
(async () => {
  if (!window.mermaid) return;
  const dark = document.body.classList.contains('vscode-dark') || document.body.classList.contains('vscode-high-contrast');
  mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: dark ? 'dark' : 'default'});
  try { const {svg} = await mermaid.render('ll-diagram', ${JSON.stringify(card.diagram).replace(/</g, '\\u003c')}); document.getElementById('diagram').innerHTML = svg; document.getElementById('flow').hidden = true; } catch {}
})();
</script>` : ''}
<script nonce="${nonce}">
const vscode = acquireVsCodeApi();
document.querySelectorAll('[data-action]').forEach(b => b.addEventListener('click', () => vscode.postMessage({action: b.dataset.action, id: ${Number(card.id)}})));
</script></body></html>`;
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function md(value) { return String(value ?? '').replace(/([\\`*_[\]<>])/g, '\\$1'); }

// ---------------------------------------------------------------------------
// Controller: polling, status bar, notifications, commands
// ---------------------------------------------------------------------------
class Controller {
  constructor(context) {
    this.context = context;
    this.api = new Api(context);
    this.provider = new CardsProvider();
    this.lens = new CardLens(this.provider);
    this.status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    this.status.show();
    this.timer = undefined;
    this.lastError = '';
  }

  card(id) { return this.provider.cards.find(c => c.id === id); }

  async start() {
    await this.refresh();
    this.schedule();
  }

  schedule() {
    clearInterval(this.timer);
    const seconds = Math.max(5, Number(vscode.workspace.getConfiguration('learnloop').get('pollSeconds')) || 15);
    this.timer = setInterval(() => { if (vscode.window.state.focused) this.refresh(); }, seconds * 1000);
  }

  async refresh() {
    const token = await this.api.token();
    await vscode.commands.executeCommand('setContext', 'learnloop.configured', Boolean(token));
    if (!token) {
      this.provider.set([]);
      this.setStatus('$(lightbulb) LearnLoop: connect', 'Click to connect LearnLoop', 'learnloop.setToken');
      return;
    }
    try {
      const data = await this.api.cards();
      this.lastError = '';
      this.notifyNew(data.cards);
      this.provider.set(data.cards);
      this.lens.refresh();
      const skills = data.skills ? `\n${data.skills.count} skills on your map · ${data.skills.level}` : '';
      this.setStatus(`$(lightbulb) ${data.unread || 0}`, `LearnLoop: ${data.unread || 0} unread card(s)${skills}`, 'learnloop.cards.focus');
    } catch (err) {
      this.setStatus('$(lightbulb) LearnLoop $(warning)', err.message, err.kind === 'unauthorized' ? 'learnloop.setToken' : 'learnloop.refresh');
      if (err.message !== this.lastError && err.kind === 'unauthorized') vscode.window.showWarningMessage(err.message, 'Set token').then(c => c && vscode.commands.executeCommand('learnloop.setToken'));
      this.lastError = err.message;
    }
  }

  setStatus(text, tooltip, command) {
    this.status.text = text;
    this.status.tooltip = tooltip;
    this.status.command = command;
  }

  notifyNew(cards) {
    const lastSeen = this.context.globalState.get(LAST_SEEN_KEY);
    const newest = cards.reduce((max, c) => Math.max(max, c.id), 0);
    if (newest) this.context.globalState.update(LAST_SEEN_KEY, Math.max(newest, lastSeen || 0));
    if (lastSeen === undefined || !vscode.workspace.getConfiguration('learnloop').get('notifications')) return; // first run: no backlog spam
    const fresh = cards.filter(c => c.id > lastSeen && !c.read && c.status !== 'known' && c.status !== 'muted').slice(0, 2);
    for (const card of fresh) {
      vscode.window.showInformationMessage(`💡 LearnLoop: ${card.concept}`, 'Explain', 'I know this').then(choice => {
        if (choice === 'Explain') this.openCard(card);
        else if (choice === 'I know this') this.setConceptStatus(card, 'known');
      });
    }
  }

  async openCard(card) {
    if (!card) return;
    showCard(card, this);
    if (!card.read) {
      card.read = true;
      this.api.act(card.id, 'read').then(() => this.refresh(), () => {});
    }
  }

  async setConceptStatus(card, action) {
    try {
      await this.api.act(card.id, action);
      vscode.window.setStatusBarMessage(action === 'known' ? `✓ ${card.concept}: marked as known` : `${card.concept}: muted`, 4000);
      await this.refresh();
      const updated = this.card(card.id);
      if (panel && updated) showCard(updated, this);
    } catch (err) {
      vscode.window.showErrorMessage(err.message);
    }
  }

  async handleCardMessage(msg) {
    const card = this.card(msg.id);
    if (!card) return;
    if (msg.action === 'known' || msg.action === 'mute') return this.setConceptStatus(card, msg.action);
    if (msg.action === 'openWeb') return vscode.env.openExternal(vscode.Uri.parse(card.url));
    if (msg.action === 'openFile') return this.goToCode(card);
  }

  async goToCode(card) {
    const file = card.file.replace(/\\/g, '/');
    let [uri] = await vscode.workspace.findFiles(file, '**/node_modules/**', 1);
    if (!uri) [uri] = await vscode.workspace.findFiles(`**/${path.basename(file)}`, '**/node_modules/**', 1);
    if (!uri) return vscode.window.showWarningMessage(`Couldn't find ${card.file} in this workspace.`);
    const doc = await vscode.workspace.openTextDocument(uri);
    const line = lineOfSnippet(doc.getText(), card.snippet);
    const editor = await vscode.window.showTextDocument(doc, vscode.ViewColumn.One);
    const range = new vscode.Range(line, 0, line, 0);
    editor.selection = new vscode.Selection(range.start, range.start);
    editor.revealRange(range, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
  }

  async setToken() {
    const url = await vscode.window.showInputBox({
      title: 'LearnLoop (1/2): server URL', value: this.api.baseUrl, ignoreFocusOut: true,
      prompt: 'Your LearnLoop server, as shown on the Setup page',
      validateInput: v => /^https?:\/\/\S+$/.test(v.trim()) ? undefined : 'Enter a URL starting with http:// or https://',
    });
    if (url === undefined) return;
    await vscode.workspace.getConfiguration('learnloop').update('serverUrl', url.trim(), vscode.ConfigurationTarget.Global);
    const token = await vscode.window.showInputBox({
      title: 'LearnLoop (2/2): your token', password: true, ignoreFocusOut: true,
      prompt: 'Paste your personal token from the Setup page (starts with ll_)',
      validateInput: v => v.trim().startsWith('ll_') ? undefined : 'LearnLoop tokens start with ll_',
    });
    if (!token) return;
    await this.context.secrets.store(TOKEN_KEY, token.trim());
    try {
      const me = await this.api.ping();
      vscode.window.showInformationMessage(`LearnLoop connected as ${me.user}.`);
    } catch (err) {
      vscode.window.showErrorMessage(err.message);
    }
    await this.refresh();
  }

  async clearToken() {
    await this.context.secrets.delete(TOKEN_KEY);
    await this.refresh();
    vscode.window.showInformationMessage('LearnLoop disconnected.');
  }

  openWeb(subpath) { vscode.env.openExternal(vscode.Uri.parse(this.api.baseUrl + subpath)); }

  dispose() { clearInterval(this.timer); this.status.dispose(); }
}

function activate(context) {
  const controller = new Controller(context);
  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, fn));
  // Tree items pass the card itself; the context menu passes the tree element, which is also the card.
  reg('learnloop.setToken', () => controller.setToken());
  reg('learnloop.clearToken', () => controller.clearToken());
  reg('learnloop.refresh', () => controller.refresh());
  reg('learnloop.openCard', card => controller.openCard(card));
  reg('learnloop.markKnown', card => card && controller.setConceptStatus(card, 'known'));
  reg('learnloop.mute', card => card && controller.setConceptStatus(card, 'mute'));
  reg('learnloop.openOnWeb', card => card && vscode.env.openExternal(vscode.Uri.parse(card.url)));
  reg('learnloop.openDashboard', () => controller.openWeb('/app/'));
  reg('learnloop.openSkillMap', () => controller.openWeb('/app/concepts/#checklist'));
  context.subscriptions.push(
    controller,
    vscode.window.registerTreeDataProvider('learnloop.cards', controller.provider),
    vscode.languages.registerCodeLensProvider({ scheme: 'file' }, controller.lens),
    vscode.workspace.onDidChangeConfiguration(e => {
      if (e.affectsConfiguration('learnloop')) { controller.schedule(); controller.refresh(); }
    }),
    vscode.window.onDidChangeWindowState(s => { if (s.focused) controller.refresh(); }),
  );
  controller.start();
  return { controller }; // exposed for tests
}

function deactivate() {}

module.exports = { activate, deactivate, _internals: { sameFile, lineOfSnippet, esc } };
