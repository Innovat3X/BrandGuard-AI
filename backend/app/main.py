from fastapi import FastAPI

app = FastAPI(
    title="BrandGuard AI API",
    version="1.0.0",
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "brandguard-ai-api",
    }
