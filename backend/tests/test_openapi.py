from httpx import AsyncClient


async def test_docs_open(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200


async def test_openapi_includes_health_and_departments(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/health" in paths
    assert "get" in paths["/api/health"]
    assert "/api/admin/departments" in paths
    assert "get" in paths["/api/admin/departments"]
    assert "post" in paths["/api/admin/departments"]
