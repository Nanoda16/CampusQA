"""根路由和健康检查端点的烟雾测试"""

from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    """GET /api/health 应返回 200 和运行状态"""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert data["code"] == 200
    assert data["message"] == "success"
    assert data["data"]["service"] == "CampusQA"
    assert data["data"]["status"] == "running"
    assert data["data"]["version"] == "1.0.0"
    assert "timestamp" in data
