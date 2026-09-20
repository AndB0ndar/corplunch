from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from inspect import iscoroutinefunction
from pathlib import Path

import httpx
import pytest

from app.providers import MealtyError, MealtyProvider, NormalizedDish, parse_html
from app.providers.mealty import MEALTY_HOMEPAGE, USER_AGENT

FIXTURE = Path(__file__).parent / "fixtures" / "mealty_catalog.html"


def _parse_fixture() -> list[NormalizedDish]:
    return parse_html(FIXTURE.read_text(encoding="utf-8"))


def _by_id(dishes: list[NormalizedDish]) -> dict[str, NormalizedDish]:
    return {dish.external_id: dish for dish in dishes}


def test_fixture_card_875_fields() -> None:
    dish = _by_id(_parse_fixture())["875"]
    assert dish.external_id == "875"
    assert dish.name == "Картофельные ньокки"
    assert dish.price_kopecks == 41000
    assert dish.category == "main_dish"
    assert dish.seller_product_id == "1530"
    assert dish.subtitle == "с томленой бараниной и баклажанами"
    assert dish.weight_g == 350
    assert dish.proteins == 6.0
    assert dish.fats == 5.0
    assert dish.carbs == 12.0
    assert dish.calories == 120.0
    assert dish.image_url == "https://www.mealty.ru/upload/88/ba/88bacf9ea2495da2.jpeg"
    assert dish.old_price_kopecks is None
    assert dish.available is True


def test_hidden_card_skipped() -> None:
    ids = {dish.external_id for dish in _parse_fixture()}
    assert "875" in ids
    assert "880" in ids
    assert "740" not in ids


def test_novelty_and_main_dish_collapse_to_one() -> None:
    dishes = _parse_fixture()
    matches = [dish for dish in dishes if dish.external_id == "875"]
    assert len(matches) == 1
    assert matches[0].category == "main_dish"


def test_parse_html_empty_returns_empty_list() -> None:
    assert parse_html("<html><body></body></html>") == []
    assert parse_html("") == []


def test_provider_source_and_fetch_is_awaitable() -> None:
    provider = MealtyProvider()
    assert provider.source == "mealty"
    assert iscoroutinefunction(provider.fetch_catalog)


@asynccontextmanager
async def _client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        yield client


async def test_fetch_catalog_empty_body_raises() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="<html><body></body></html>")

    async with _client(handler) as client:
        provider = MealtyProvider(city="Москва", client=client)
        with pytest.raises(MealtyError):
            await provider.fetch_catalog()
    assert len(requests) == 1
    assert str(requests[0].url) == MEALTY_HOMEPAGE
    assert requests[0].url.path == "/"
    assert "city_id=1" in requests[0].headers.get("cookie", "")
    assert requests[0].headers.get("user-agent") == USER_AGENT


async def test_fetch_catalog_uses_moscow_cookie_and_homepage_only() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=html)

    async with _client(handler) as client:
        provider = MealtyProvider(city="Москва", client=client)
        dishes = await provider.fetch_catalog()
    assert {dish.external_id for dish in dishes} == {"875", "880"}
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == MEALTY_HOMEPAGE
    assert request.method == "GET"
    assert request.url.host == "www.mealty.ru"
    assert request.url.path == "/"
    assert "/ajax.php" not in str(request.url)
    assert "/cabinet" not in str(request.url)
    assert "/city" not in str(request.url)
    assert "city_id=1" in request.headers.get("cookie", "")


async def test_unknown_city_raises_before_http() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not request Mealty for an unknown city")

    async with _client(handler) as client:
        provider = MealtyProvider(city="Париж", client=client)
        with pytest.raises(MealtyError, match="Unknown Mealty city"):
            await provider.fetch_catalog()


async def test_http_502_after_retry_raises() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(502, text="bad gateway")

    async with _client(handler) as client:
        provider = MealtyProvider(city="Москва", client=client)
        with pytest.raises(MealtyError):
            await provider.fetch_catalog()
    assert attempts == 2
