from typing import Protocol

from pydantic import BaseModel


class NormalizedDish(BaseModel):
    external_id: str
    seller_product_id: str | None
    name: str
    subtitle: str
    description: str | None
    category: str
    price_kopecks: int
    old_price_kopecks: int | None
    weight_g: int | None
    proteins: float | None
    fats: float | None
    carbs: float | None
    calories: float | None
    image_url: str | None
    available: bool


class FoodProvider(Protocol):
    source: str

    async def fetch_catalog(self) -> list[NormalizedDish]: ...
