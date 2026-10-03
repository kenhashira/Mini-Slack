from fastapi import Depends, FastAPI

from app.deps import current_user_id
from app.errors import register_error_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="Mini-Slack", version="0.1.0")
    register_error_handlers(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/me")
    def me(user_id: str = Depends(current_user_id)):
        return {"user_id": user_id}

    return app


app = create_app()
