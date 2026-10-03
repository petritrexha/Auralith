# LearnLoop for VS Code

*Learn what your AI just built, while it builds it.*

The Claude Code plugin captures what the agent changed and the LearnLoop server writes short "why it's here" cards.
This extension brings those cards into the editor:

- **Sidebar** (💡 icon in the activity bar): every card, unread ones highlighted. Hover for the summary.
- **Card panel**: summary, "why it's here", the real snippet, official docs, plus **I know this**, **Don't explain again**, **Go to code** and **Open on the web**.
- **CodeLens**: `💡 LearnLoop: <concept>` right above the code a card explains.
- **Notifications** when a new card arrives, and an unread counter in the status bar.

It uses the same personal token as the Claude Code plugin. No dependencies, no build step.

## What you need

| Need | Why |
| --- | --- |
| VS Code 1.90 or newer | Built-in `fetch` and the APIs used here |
| A running LearnLoop server | Locally: `python manage.py runserver` in `server/` |
| Your LearnLoop token | LearnLoop → Setup page (starts with `ll_`) |
| Node.js (only to build a `.vsix`) | `npx @vscode/vsce package` |
| A Marketplace publisher (optional) | Only to publish publicly; a `.vsix` is enough for a demo |

## Step by step

### 1. Run it in development (fastest)
1. Open the repo root in VS Code.
2. Start the server: `cd server`, activate the venv, `python manage.py runserver`.
3. Press **F5** and pick **Run LearnLoop VS Code extension** (from `.vscode/launch.json`). A second VS Code window opens with the extension loaded.
4. In that window, click the 💡 LearnLoop icon in the activity bar → **Connect with my token**.
5. Enter the server URL (`http://127.0.0.1:8000`) and paste your token. You should see "LearnLoop connected as …".
6. Code with Claude Code as usual. When a card is created, a notification pops up, it appears in the sidebar, and a 💡 lens shows above the code.

Edit `extension.js`, then press **Ctrl+R** in the extension window (or the restart button on the debug toolbar) to reload.

### 2. Install it for real (a `.vsix` file)
```powershell
cd vscode-extension
npx --yes @vscode/vsce package --allow-missing-repository
code --install-extension learnloop-0.1.0.vsix
```
Send the same `.vsix` to teammates: VS Code → Extensions → `…` menu → **Install from VSIX…**

### 3. Publish to the Marketplace (optional, later)
1. Create a publisher at https://marketplace.visualstudio.com/manage and set `"publisher"` in `package.json` to its id.
2. Create an Azure DevOps personal access token with the *Marketplace (Manage)* scope.
3. Add a `repository` field and a 128×128 PNG `icon` to `package.json`.
4. `npx @vscode/vsce login <publisher>` then `npx @vscode/vsce publish`.

## Settings

| Setting | Default | |
| --- | --- | --- |
| `learnloop.serverUrl` | `http://127.0.0.1:8000` | Your LearnLoop server |
| `learnloop.pollSeconds` | `15` | How often to check for new cards (only while VS Code is focused) |
| `learnloop.notifications` | `true` | Pop-up when a new card arrives |
| `learnloop.codeLens` | `true` | 💡 lens above code that has a card |

The token is kept in VS Code's secret storage (OS keychain), never in settings.

## How it talks to the server
- `GET /api/v1/cards?limit=40`: recent cards, unread count, skill-map progress.
- `POST /api/v1/cards/<id>/action` with `{"action": "read" | "known" | "mute" | "save" | "unsave"}`.
- `GET /api/v1/ping`: connection check.

All use `Authorization: Bearer <token>`, exactly like the Claude Code plugin.

## Ideas for next versions
- "Explain this selection" command (send selected code to a new `/api/v1/explain` endpoint).
- Hover provider instead of / in addition to CodeLens.
- Show the skill map inside VS Code (webview) so people can tick skills without leaving the editor.
- Server push (SSE) instead of polling.
