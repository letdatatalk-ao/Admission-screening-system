from fastapi import FastAPI

app = FastAPI(
    title="PGARS API",
    description="Postgraduate Applicant Screening and Ranking System",
    version="1.0.0"
)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "PGARS Backend"}