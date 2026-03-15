# AI Data Explorer EU

Author: Inari Solutions Sp. z o.o.

## Description

AI Data Explorer EU is a hackathon demonstration application for searching and exploring datasets from data.europa.eu through a web interface with an embedded AI agent, backed by FastAPI and Azure AI services.

> **Hackathon Submission:** See [HACKATHON.md](HACKATHON.md) for the full project documentation, architecture, and feature overview prepared for the Microsoft AI Dev Days Hackathon 2026.

The project consists of two main parts:

- `backend/` - API, conversation handling, Azure AI integration, and dataset search logic.
- `frontend/` - static HTML/CSS/JS user interface for interacting with the on-page agent and reviewing results.

## Project Status

This is demonstration code prepared for a hackathon.

The project is not ready for production use.

Before any production deployment, it should at minimum undergo:

- a security review,
- automated and integration testing,
- environment and configuration hardening,
- validation of error handling, logging, and monitoring,
- release and maintenance process preparation.

## Requirements

The backend uses Python and the dependencies listed in `backend/requirements.txt`.

Running the backend requires Azure environment variables, in particular:

- `AZURE_AI_PROJECT_ENDPOINT`
- `AZURE_AI_AGENT_NAME`
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`
- `AZURE_AI_AGENT_VERSION`


## Example Backend Startup

From the `backend/` directory:

```bash
python -m venv antenv
source antenv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Alternatively, you can use the `startup.sh` script.

## Frontend

The frontend is located in `frontend/` and can be served as a static web application. The default entry document is `frontend/index.html`.

When the frontend is hosted separately from the backend, set the backend URL in `frontend/config.js`. A template is provided in `frontend/config.example.js`:

```javascript
window.__API_BASE__ = "https://your-backend-host.example.com";
```

The frontend loads `config.js` before `app.js`, so this value can be changed at deployment time without rebuilding the application.

### Frontend Setup

```bash
# From the repository root
python -m http.server 8080 --directory frontend
# Open http://localhost:8080
```

> **Note:** `frontend/config.js` is deployment-specific and is ignored by git. Use `frontend/config.example.js` as the template and set the public backend URL before deploying or serving the frontend from a separate host.

## License

This project is distributed under the MIT License. The full license text is available in [LICENSE](LICENSE).