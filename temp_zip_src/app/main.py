from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
import os

from app.config import APP_NAME, API_PREFIX
from app.database import check_db_status
from app.services.audit_service import get_dashboard_summary

app = FastAPI(title=APP_NAME, version="1.0.0")

# Mount static files and templates using relative module pathing
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.get("/")
def read_root(request: Request):
    """Render main Mini Financial Audit Tool Dashboard."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"app_name": APP_NAME}
    )

@app.get(f"{API_PREFIX}/health")
def health_check():
    """Health check endpoint displaying Read-Only database connection status."""
    db_status = check_db_status()
    return JSONResponse(content={
        "status": "online",
        "app": APP_NAME,
        "database": db_status
    })

@app.get(f"{API_PREFIX}/summary")
def get_summary():
    """
    Returns aggregated KPI metrics and audit summary counts.
    STRICT SECURITY GUARANTEE: Zero raw rows or PII fields exposed.
    """
    summary_data = get_dashboard_summary()
    return JSONResponse(content=summary_data)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
