# Backend

FastAPI foundation for the SAFe DevOps Adaptive Assessment.

## Local

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATA_DIR=../data
export ADMIN_PASSWORD_HASH="$(python ../scripts/hash_admin_password.py --password 'change-me')"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Tests

```bash
pytest
```
