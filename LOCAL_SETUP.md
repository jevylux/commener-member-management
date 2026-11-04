# Local Development Setup

## Quick Start

1. **Run the setup script:**
   ```bash
   chmod +x setup_venv.sh
   ./setup_venv.sh
   ```

2. **Activate the virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

3. **Start the Flask app:**
   ```bash
   python run.py
   ```

4. **Open in browser:**
   http://localhost:5000

## VS Code Integration

Open the folder in VS Code. The `.vscode/settings.json` automatically configures:
- Python interpreter from `.venv`
- Terminal auto-activation
- Debug configuration

Press `F5` or go to **Run → Start Debugging** to launch the Flask app with debugger.

## Database

Local development uses SQLite: `database/commEnergy.db`

The database path is configured in `config.py`:
```python
SQLALCHEMY_DATABASE_URI = 'sqlite:///database/commEnergy.db'
```

## Environment Variables (optional)

Create a `.env` file for secrets:
```bash
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///database/commEnergy.db
```
