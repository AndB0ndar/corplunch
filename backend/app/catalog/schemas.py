from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DishOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
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


class CatalogSyncOut(BaseModel):
    upserted: int
    unavailable: int
    recorded_at: datetime
