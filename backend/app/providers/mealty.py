from __future__ import annotations

import re
from typing import Final

import httpx
from bs4 import BeautifulSoup, Tag

from app.config import settings
from app.providers.base import NormalizedDish

MEALTY_HOMEPAGE: Final = "https://www.mealty.ru/"
MEALTY_ORIGIN: Final = "https://www.mealty.ru"
USER_AGENT: Final = "CorpLunch/0.1 (course project; contact: corplunch@kis.local)"
TIMEOUT_SECONDS: Final = 20.0
CITY_IDS: Final = {
    "Москва": "1",
    "Санкт-Петербург": "2",
}

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


class MealtyError(Exception):
    """Raised when the Mealty homepage cannot be fetched or parsed."""


def city_id_for(city: str) -> str:
    city_id = CITY_IDS.get(city)
    if city_id is None:
        raise MealtyError(f"Unknown Mealty city: {city}")
    return city_id


def parse_html(html: str) -> list[NormalizedDish]:
    soup = BeautifulSoup(html, "lxml")
    by_external_id: dict[str, NormalizedDish] = {}

    for item in soup.select(".catalog-item"):
        if _has_class(item, "hidden"):
            continue
        dish = _parse_card(item)
        if dish is None:
            continue
        existing = by_external_id.get(dish.external_id)
        if existing is None:
            by_external_id[dish.external_id] = dish
            continue
        if existing.category == "novelty" and dish.category != "novelty":
            by_external_id[dish.external_id] = existing.model_copy(
                update={"category": dish.category}
            )

    return list(by_external_id.values())


class MealtyProvider:
    source: str = "mealty"

    def __init__(
        self,
        *,
        city: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._city = city
        self._client = client

    async def fetch_catalog(self) -> list[NormalizedDish]:
        city_id = city_id_for(self._resolve_city())
        if self._client is not None:
            html = await self._download(self._client, city_id)
        else:
            async with httpx.AsyncClient() as client:
                html = await self._download(client, city_id)
        dishes = parse_html(html)
        if not dishes:
            raise MealtyError("Mealty catalog contained no visible dishes")
        return dishes

    def _resolve_city(self) -> str:
        return self._city if self._city is not None else settings.mealty_city

    async def _download(self, client: httpx.AsyncClient, city_id: str) -> str:
        last_status: int | None = None
        for attempt in range(2):
            retry = attempt == 0
            try:
                response = await client.get(
                    MEALTY_HOMEPAGE,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Cookie": f"city_id={city_id}",
                    },
                    timeout=TIMEOUT_SECONDS,
                    follow_redirects=False,
                )
            except httpx.RequestError as exc:
                if retry:
                    continue
                raise MealtyError("Mealty request failed") from exc
            if response.status_code >= 500:
                last_status = response.status_code
                if retry:
                    continue
                raise MealtyError(f"Mealty HTTP {response.status_code}")
            if response.status_code >= 400:
                raise MealtyError(f"Mealty HTTP {response.status_code}")
            return response.text
        raise MealtyError(f"Mealty HTTP {last_status}")


def _parse_card(item: Tag) -> NormalizedDish | None:
    external_id = (item.get("data-product_id") or "").strip()
    if not external_id:
        return None
    name = _child_text(item, ".meal-card__name")
    if not name:
        return None
    price_el = item.select_one(".meal-card__price[data-price]")
    price_kopecks = _attr_to_kopecks(
        price_el.get("data-price") if price_el is not None else None
    )
    if price_kopecks is None:
        return None
    seller = item.get("data-seller-product_id") or item.select_one(
        "[data-seller-product_id]"
    )
    seller_product_id: str | None
    if isinstance(seller, Tag):
        seller_product_id = (seller.get("data-seller-product_id") or "").strip() or None
    else:
        seller_product_id = (seller or "").strip() or None

    return NormalizedDish(
        external_id=external_id,
        seller_product_id=seller_product_id,
        name=name,
        subtitle=_child_text(item, ".meal-card__name-note"),
        description=_nullable_text(_child_text(item, ".meal-card__description")),
        category=_enclosing_category(item),
        price_kopecks=price_kopecks,
        old_price_kopecks=_old_price_kopecks(item),
        weight_g=_parse_int(_child_text(item, ".meal-card__weight")),
        proteins=_parse_float(_child_text(item, ".meal-card__proteins")),
        fats=_parse_float(_child_text(item, ".meal-card__fats")),
        carbs=_parse_float(_child_text(item, ".meal-card__carbohydrates")),
        calories=_parse_float(_child_text(item, ".meal-card__calories")),
        image_url=_image_url(item),
        available=True,
    )


def _enclosing_category(item: Tag) -> str:
    for parent in item.parents:
        parent_id = parent.get("id") if isinstance(parent, Tag) else None
        if parent_id:
            return parent_id
    return "unknown"


def _image_url(item: Tag) -> str | None:
    root = item.select_one(".meal-card__image")
    if root is None:
        return None
    lazy = root.select_one("img.lazy[data-src]")
    src = (lazy.get("data-src") if lazy is not None else None) or ""
    if not src:
        for img in root.select("img[data-src]"):
            candidate = img.get("data-src") or ""
            if candidate.startswith("/upload/"):
                src = candidate
                break
    if not src or "gray_bg_604x604.gif" in src:
        return None
    return _absolute_url(src)


def _absolute_url(src: str) -> str:
    if src.startswith("http://") or src.startswith("https://"):
        return src
    if src.startswith("/"):
        return MEALTY_ORIGIN + src
    return f"{MEALTY_ORIGIN}/{src}"


def _old_price_kopecks(item: Tag) -> int | None:
    el = item.select_one(".meal-card__price-old")
    if el is None:
        return None
    from_attr = _attr_to_kopecks(el.get("data-price"))
    if from_attr is not None:
        return from_attr
    return _to_kopecks(_text(el))


def _child_text(item: Tag, selector: str) -> str:
    el = item.select_one(selector)
    return _text(el) if el is not None else ""


def _text(el: Tag) -> str:
    return " ".join(el.get_text().split())


def _nullable_text(value: str) -> str | None:
    return value or None


def _has_class(tag: Tag, name: str) -> bool:
    classes = tag.get("class")
    if isinstance(classes, str):
        return name in classes.split()
    if isinstance(classes, list):
        return name in classes
    return False


def _parse_float(value: str) -> float | None:
    normalized = value.replace("\xa0", " ").replace(" ", "").replace(",", ".")
    match = _NUMBER_RE.search(normalized)
    if match is None:
        return None
    return float(match.group())


def _parse_int(value: str) -> int | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _attr_to_kopecks(value: str | list[str] | None) -> int | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if not value:
        return None
    return _to_kopecks(value)


def _to_kopecks(value: str) -> int | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    return int(round(parsed * 100))
