import os
import sys
from pathlib import Path

# Ensure standalone_budget_app is on sys.path regardless of where run.py is invoked from
APP_DIR = Path(__file__).resolve().parent
os.chdir(APP_DIR)
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import uvicorn
from config import settings
from seeds.seed_standalone_db import initialize_and_seed_standalone_db

if __name__ == "__main__":
    print("=" * 72)
    print("  Standalone Departmental Budget Allocation & Savings Analytics")
    print(f"  SQLite DB : {APP_DIR / 'budget_standalone.db'}")
    print(f"  Server URL: http://127.0.0.1:{settings.PORT}/budget-dashboard")
    print("=" * 72)
    initialize_and_seed_standalone_db()
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
