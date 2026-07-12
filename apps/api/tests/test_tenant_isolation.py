from tests.conftest import bootstrap


def test_brand_and_product_are_scoped_to_organization(client, auth):
    brand = client.post(
        "/v1/brands",
        headers=auth,
        json={"name": "Field Light", "story": "A verified story", "voice": "Warm"},
    )
    assert brand.status_code == 201
    product = client.post(
        "/v1/products",
        headers=auth,
        json={
            "brand_id": brand.json()["id"],
            "name": "Synthetic Demo Mushroom",
            "origin": "Demo County",
            "selling_points": ["Traceable batch"],
            "prohibited_claims": ["Cures anxiety"],
        },
    )
    assert product.status_code == 201

    second = bootstrap(client, "river-farm", "owner@river.example")
    second_auth = {"Authorization": f"Bearer {second['access_token']}"}

    assert client.get("/v1/brands", headers=second_auth).json() == []
    assert client.get("/v1/products", headers=second_auth).json() == []

    cross_tenant_product = client.post(
        "/v1/products",
        headers=second_auth,
        json={"brand_id": brand.json()["id"], "name": "Forbidden product"},
    )
    assert cross_tenant_product.status_code == 404


def test_invalid_token_is_rejected(client):
    response = client.get("/v1/brands", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
