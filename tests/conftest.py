import pytest


@pytest.fixture(params=["IFC2X3", "IFC4", "IFC4X3"])
def schema(request: pytest.FixtureRequest) -> str:
    """Every test taking ``schema`` runs once per supported IFC schema."""
    return request.param
