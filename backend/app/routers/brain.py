"""AI Business Brain: daily brief from live data only."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..brain import daily_brief
from ..db import get_db

router = APIRouter()


@router.get("/reports/brief")
def brief(db: Session = Depends(get_db)):
    return daily_brief(db)
