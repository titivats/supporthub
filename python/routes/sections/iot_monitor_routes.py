from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session


def register_iot_monitor_routes(app, templates, ctx):
    get_db = ctx["get_db"]
    iot_monitor = ctx["iot_monitor"]
    get_current_user = ctx["get_current_user"]

    @app.get("/iot-monitor", response_class=HTMLResponse)
    def iot_monitor_page(request: Request, db: Session = Depends(get_db)):
        try:
            user = get_current_user(request, db)
        except HTTPException:
            return RedirectResponse("/login", status_code=302)
        return templates.TemplateResponse(
            "iot_monitor.html",
            {
                "request": request,
                "user": user,
            },
        )

    @app.get("/api/iot-monitor/status")
    def api_iot_monitor_status(request: Request, db: Session = Depends(get_db)):
        _ = get_current_user(request, db)
        return iot_monitor.snapshot()

    @app.post("/api/iot-monitor/reconnect")
    async def api_iot_monitor_reconnect(request: Request, db: Session = Depends(get_db)):
        _ = get_current_user(request, db)
        try:
            body = await request.json()
        except Exception:
            body = {}
        result = iot_monitor.reconnect(
            host=body.get("host"),
            port=int(body["port"]) if body.get("port") else None,
            topic=body.get("topic"),
            client_id=body.get("client_id"),
        )
        return {"ok": True, **result}
