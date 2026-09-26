# Talegaon Fresh AI Backend

WhatsApp AI ordering backend for Talegaon Fresh.

## Stack
- Python
- FastAPI
- OpenAI API
- WhatsApp Cloud API
- MySQL (next phase)

## Local setup

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Environment variables are documented in `.env.example`. Never commit secrets.
