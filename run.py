import uvicorn
from app.config import settings

if __name__ == "__main__":
    print(f"🚀 Starting {settings.APP_NAME} on http://localhost:{settings.PORT}")
    print(f"📖 Swagger interactive API docs: http://localhost:{settings.PORT}/docs")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=settings.PORT,
        reload=True,
    )

