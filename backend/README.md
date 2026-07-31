# Backend

FastAPI foundation for the SAFe DevOps Adaptive Assessment.

## Local

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATA_DIR=../data
export APP_SECRET_KEY='local-dev-app-secret-key-change-me'
# Optional dedicated admin password (APP_SECRET_KEY is also accepted at login):
# export ADMIN_PASSWORD_HASH="$(python ../scripts/hash_admin_password.py --password 'change-me')"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Tests

```bash
pytest
```
