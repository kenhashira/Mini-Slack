from fastapi import Depends, FastAPI

from app.db import init_db, resolve_db_path
from app.deps import current_user_id
from app.errors import register_error_handlers


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="Mini-Slack", version="0.1.0")
    app.state.db_path = resolve_db_path(db_path)
    init_db(app.state.db_path)
    register_error_handlers(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/me")
    def me(user_id: str = Depends(current_user_id)):
        return {"user_id": user_id}

    return app


app = create_app()
