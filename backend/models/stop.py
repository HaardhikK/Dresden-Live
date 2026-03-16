"""
Data model for a transit stop.
"""
from pydantic import BaseModel


class Stop(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    city: str = "Dresden"
