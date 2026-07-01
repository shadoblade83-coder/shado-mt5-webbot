# Shado MT5 Web Bot

A simple GitHub-ready dashboard for controlling a local MetaTrader 5 Python bridge.

Important: GitHub Pages can host the dashboard, but it cannot run the Python bot. The backend must run on your Windows PC or VPS where MetaTrader 5 is installed and logged in.

## What is included

- `frontend/` — static website dashboard for GitHub Pages.
- `backend/` — FastAPI server that talks to MetaTrader 5 through the Python package.
- Paper/logging mode by default.
- Optional live mode locked behind `LIVE_TRADING_ENABLED=true`.
- Status checker, candle chart, bot start/stop, manual test order, and bot logs.
- Replaceable example SMA crossover strategy.

## Safety defaults

The project starts in paper mode. Live trading is blocked until you deliberately edit `backend/.env`.

This is infrastructure code, not a profitable strategy. Test on a demo account first.

## Requirements

- Windows PC or Windows VPS recommended.
- MetaTrader 5 terminal installed.
- Python 3.10+.
- A MetaTrader 5 demo account while testing.

## Run locally in VS Code

1. Open this folder in VS Code.
2. Open a terminal in VS Code.
3. Create a virtual environment:

```bash
cd backend
python -m venv .venv
```

4. Activate it:

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Command Prompt:

```bat
.venv\Scripts\activate.bat
```

5. Install packages:

```bash
pip install -r requirements.txt
```

6. Create your environment file:

```bash
copy .env.example .env
```

7. Open MetaTrader 5 on your PC and log in to your demo account.

8. Start the backend:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

9. Open `frontend/index.html` in your browser, or use VS Code Live Server.

## Put the dashboard on GitHub Pages

1. Create a new GitHub repository, for example `shado-mt5-webbot`.
2. Upload all project files.
3. Go to **Settings → Pages**.
4. Under **Build and deployment**, choose **Deploy from a branch**.
5. Choose your `main` branch and set the folder to `/frontend` if GitHub shows that option.
6. Save. GitHub will give you a public URL.

If GitHub Pages does not allow `/frontend` directly, move the files inside `frontend/` to the root of the repository, or use GitHub Actions later.

## How the bot connects

Browser dashboard → FastAPI backend running on your PC/VPS → MetaTrader 5 terminal → broker/demo account.

A public GitHub Pages website cannot connect to MT5 by itself. It must call your running backend.

## Unlock live mode only after demo testing

In `backend/.env`:

```env
LIVE_TRADING_ENABLED=true
API_SECRET=put-a-long-secret-here
```

Then restart the backend.

When live mode is enabled, the dashboard must send the same API key in the API key field.

## Where to edit the strategy

Open `backend/main.py` and find:

```python
def crossover_signal(...):
```

Replace that function with your own rule. Keep it returning only:

- `"buy"`
- `"sell"`
- `"hold"`

## Useful next upgrades

- Real backtesting module before any live deployment.
- Trade journal database.
- Daily loss limit based on account history.
- Better chart library.
- Login system if the backend is exposed on the internet.
- VPS deployment so the bot keeps running when your laptop is off.
