"""Unit tests for CatalogSearch using mocked S3 catalog data."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.app.catalog import CatalogSearch
from backend.app.s3_client import S3DownloadError


def _build_catalog_data() -> dict[str, Any]:
    """Build catalog index data covering categories and capacity variants.

    Returns:
        dict[str, Any]: Catalog payload matching the expected schema.
    """

    return {
        "productos": [
            {
                "id": "panel-1",
                "nombre_comercial": "SolTech Alpha 400",
                "categoria": "paneles",
                "fabricante": "SolTech",
                "ruta_s3": "raw/paneles/soltech-alpha-400.pdf",
                "subcategoria": "Monocristalino",
                "parametros_comunes": {"tipo": "Monocristalino"},
                "variantes": [
                    {
                        "nombre": "Alpha 400",
                        "parametros_clave": {"potencia_w": 400},
                    },
                    {
                        "nombre": "Alpha 420",
                        "parametros_clave": {"potencia_w": 420},
                    },
                ],
            },
            {
                "id": "inversor-1",
                "nombre_comercial": "ElectroMax Grid 5k",
                "categoria": "inversores",
                "fabricante": "ElectroMax",
                "ruta_s3": "raw/inversores/electromax-grid-5k.pdf",
                "subcategoria": "String",
                "parametros_comunes": {"tipo": "String"},
                "variantes": [
                    {
                        "nombre": "Grid 5k",
                        "parametros_clave": {"capacidad_wh": 5000},
                    }
                ],
            },
            {
                "id": "controlador-1",
                "nombre_comercial": "PowerFlow MPPT 80A",
                "categoria": "controladores",
                "fabricante": "PowerFlow",
                "ruta_s3": "raw/controladores/powerflow-mppt-80a.pdf",
                "subcategoria": "MPPT",
                "parametros_comunes": {"tipo": "MPPT"},
                "variantes": [
                    {
                        "nombre": "MPPT 80A",
                        "parametros_clave": {"capacidad_a": 80},
                    },
                    {
                        "nombre": "MPPT 60A",
                        "parametros_clave": {"capacidad_a": 60},
                    },
                ],
            },
            {
                "id": "controlador-2",
                "nombre_comercial": "MicroCurrent PWM 40A",
                "categoria": "controladores",
                "fabricante": "MicroCurrent",
                "ruta_s3": "raw/controladores/microcurrent-pwm-40a.pdf",
                "subcategoria": "PWM",
                "parametros_comunes": {"tipo": "PWM"},
                "variantes": [
                    {
                        "nombre": "PWM 40A",
                        "parametros_clave": {"capacidad_a": 40},
                    }
                ],
            },
            {
                "id": "bateria-1",
                "nombre_comercial": "UltraStorage LiFePO4 10kWh",
                "categoria": "baterias",
                "fabricante": "UltraStorage",
                "ruta_s3": "raw/baterias/ultrastorage-lifepo4-10kwh.pdf",
                "subcategoria": "Litio",
                "parametros_comunes": {"tipo": "Litio"},
                "variantes": [
                    {
                        "nombre": "10kWh",
                        "parametros_clave": {"capacidad_wh": 10000},
                    }
                ],
            },
        ]
    }


@pytest.fixture
def catalog_data() -> dict[str, Any]:
    """Provide catalog data for test cases."""

    return _build_catalog_data()


@pytest.fixture
def catalog_bytes(catalog_data: dict[str, Any]) -> bytes:
    """Serialize catalog data into UTF-8 encoded bytes."""

    return json.dumps(catalog_data).encode("utf-8")


@pytest.fixture
def mock_s3_client(catalog_bytes: bytes) -> MagicMock:
    """Return mocked S3 client returning provided catalog bytes."""

    mock_client = MagicMock()
    mock_client.download_pdf.return_value = catalog_bytes
    return mock_client


@pytest.fixture
def catalog_search(mock_s3_client: MagicMock) -> CatalogSearch:
    """Instantiate CatalogSearch with a mocked S3 client."""

    return CatalogSearch(mock_s3_client)


def test_search_by_categoria_returns_list(catalog_search: CatalogSearch) -> None:
    """Ensure category filter returns list limited to matching products."""

    resultados = catalog_search.search(categoria="paneles")

    assert isinstance(resultados, list)
    assert len(resultados) == 1
    assert resultados[0]["categoria"] == "paneles"


def test_search_by_fabricante_filters_correctly(catalog_search: CatalogSearch) -> None:
    """Validate case-insensitive fabricante substring filtering."""

    resultados = catalog_search.search(categoria="inversores", fabricante="MAX")

    assert len(resultados) == 1
    assert resultados[0]["fabricante"] == "ElectroMax"


def test_search_by_capacidad_min_filters_correctly(
    catalog_search: CatalogSearch,
) -> None:
    """Ensure capacidad_min filter keeps products with qualifying variants."""

    resultados = catalog_search.search(categoria="controladores", capacidad_min=70)

    assert len(resultados) == 1
    assert resultados[0]["id"] == "controlador-1"


def test_search_by_tipo_filters_correctly(catalog_search: CatalogSearch) -> None:
    """Verify tipo filter matches tipo/subcategoria fields case-insensitively."""

    resultados = catalog_search.search(categoria="controladores", tipo="pwm")

    assert len(resultados) == 1
    assert resultados[0]["subcategoria"].lower() == "pwm"


def test_search_no_results_returns_empty_list(catalog_search: CatalogSearch) -> None:
    """Confirm empty list is returned when no products match the category."""

    resultados = catalog_search.search(categoria="bombas")

    assert resultados == []


def test_catalog_unavailable_returns_empty_list_without_raising() -> None:
    """Ensure S3 download errors are swallowed and an empty list is returned."""

    mock_s3_client = MagicMock()
    mock_s3_client.download_pdf.side_effect = S3DownloadError("unavailable")
    catalog_search = CatalogSearch(mock_s3_client)

    resultados = catalog_search.search(categoria="paneles")

    assert resultados == []
