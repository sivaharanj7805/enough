"""Unsubscribe endpoint — CAN-SPAM/CASL compliance."""

import logging
import re

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(
    email: str = Query(..., description="Email to unsubscribe", max_length=320),
    db: asyncpg.Connection = Depends(get_db),
):
    """Unsubscribe an email from all marketing communications."""
    cleaned = email.lower().strip()
    if not _EMAIL_RE.match(cleaned):
        raise HTTPException(400, "Invalid email address")

    await db.execute(
        """INSERT INTO email_optouts (email) VALUES ($1)
           ON CONFLICT (email) DO NOTHING""",
        cleaned,
    )
    logger.info("Unsubscribed: %s", cleaned)

    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Unsubscribed — Tended</title>
  <style>
    body { font-family: 'Inter', system-ui, sans-serif; background: #f8fafc; color: #1e293b; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
    .card { background: #fff; border-radius: 12px; padding: 48px; max-width: 480px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    h1 { font-size: 24px; margin: 0 0 12px; }
    p { color: #64748b; font-size: 15px; line-height: 1.6; margin: 0; }
    .check { font-size: 48px; margin-bottom: 16px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="check">&#10003;</div>
    <h1>You've been unsubscribed</h1>
    <p>You won't receive any more emails from Tended. If this was a mistake, just submit a new audit at <a href="https://usetended.io" style="color:#16a34a;">usetended.io</a>.</p>
  </div>
</body>
</html>""", status_code=200)
