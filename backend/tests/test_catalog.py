"""Unit tests for structured catalog filtering."""

from typing import Any, Dict

import pytest

from backend.app.catalog import Catalog


@pytest.fixture
def catalog_data() -> Dict[str, Any]:
    """Return catalog data with valid, absent, and malformed optional values."""
    return {
        "productos": [
            {
                "nombre_comercial": "Jinko Tiger Pro",
                "fabricante": "Jinko Solar",
                "categoria": "paneles",
                "descripcion": "Panel with no type clues in its name",
                "ruta_s3": "raw/paneles/jinko.pdf",
                "parametros_comunes": {"tipo_celda": "monocristalino"},
                "variantes": [
                    {
                        "modelo": "JKM-400",
                        "parametros_clave": {"potencia_w": 400},
                    },
                    {
                        "modelo": "JKM-500",
                        "parametros_clave": {"potencia_w": "500"},
                    },
                ],
            },
            {
                "nombre_comercial": "Growatt Mixed",
                "fabricante": "Growatt",
                "categoria": "inversores",
                "ruta_s3": "raw/inversores/growatt.pdf",
                "parametros_comunes": {"tipo": "multifuncional"},
                "variantes": [
                    {
                        "modelo": "MIN-3000",
                        "parametros_clave": {"capacidad": 3000},
                    },
                    {
                        "modelo": "GRID-5000",
                        "parametros_clave": {
                            "capacidad": 5000,
                            "tipo": "conexion_a_red",
                        },
                    },
                ],
            },
            {
                "nombre_comercial": "Malformed Capacity",
                "fabricante": "Growatt",
                "categoria": "inversores",
                "ruta_s3": "raw/inversores/malformed.pdf",
                "parametros_comunes": {"tipo": "multifuncional"},
                "variantes": [
                    {
                        "modelo": "BAD-TEXT",
                        "parametros_clave": {"capacidad": "unknown"},
                    },
                    {
                        "modelo": "BAD-BOOL",
                        "parametros_clave": {"capacidad": True},
                    },
                    {
                        "modelo": "BAD-NAN",
                        "parametros_clave": {"capacidad": float("nan")},
                    },
                    {"modelo": "MISSING", "parametros_clave": {}},
                ],
            },
            {
                "nombre_comercial": "Type Only In Name MPPT",
                "fabricante": "Victron",
                "categoria": "controladores",
                "descripcion": "An MPPT controller",
                "ruta_s3": "raw/controladores/missing-type.pdf",
                "parametros_comunes": {},
                "variantes": [
                    {
                        "modelo": "MPPT-100",
                        "parametros_clave": {"capacidad_a": 100},
                    }
                ],
            },
            {
                "nombre_comercial": "Malformed Type",
                "fabricante": "Victron",
                "categoria": "controladores",
                "ruta_s3": "raw/controladores/malformed-type.pdf",
                "parametros_comunes": {"tipo": 123},
                "variantes": [
                    {
                        "modelo": "CTRL-100",
                        "parametros_clave": {"capacidad_a": 100},
                    }
                ],
            },
        ]
    }


@pytest.fixture
def catalog(catalog_data: Dict[str, Any]) -> Catalog:
    """Build a catalog from the test data."""
    return Catalog(catalog_data)


def test_search_without_optional_filters_preserves_all_products(
    catalog: Catalog,
) -> None:
    """Absent optional filters must not reject incomplete catalog entries."""
    assert len(catalog.search()) == 5


@pytest.mark.parametrize(
    ("minimum", "maximum", "expected_names"),
    [
        (400, 400, ["Jinko Tiger Pro"]),
        (500, 500, ["Jinko Tiger Pro"]),
        (401, 499, []),
        (None, 400, ["Jinko Tiger Pro"]),
        (500, None, ["Jinko Tiger Pro"]),
    ],
)
def test_search_applies_inclusive_normalized_capacity_boundaries(
    catalog: Catalog,
    minimum: float | None,
    maximum: float | None,
    expected_names: list[str],
) -> None:
    """Capacity bounds are inclusive and normalize numeric strings."""
    results = catalog.search(
        categoria="paneles",
        capacidad_min=minimum,
        capacidad_max=maximum,
    )

    assert [product.nombre_comercial for product in results] == expected_names


def test_search_excludes_missing_and_malformed_capacity_values(
    catalog: Catalog,
) -> None:
    """Malformed capacities do not match an active numeric filter."""
    assert catalog.search(
        categoria="inversores",
        fabricante="Growatt",
        capacidad_min=0,
    ) == [catalog.products[1]]


@pytest.mark.parametrize(
    ("category", "product_type", "expected_names"),
    [
        ("paneles", "MONOCRISTALINO", ["Jinko Tiger Pro"]),
        ("inversores", "multifuncional", ["Growatt Mixed", "Malformed Capacity"]),
        ("inversores", "conexion_a_red", ["Growatt Mixed"]),
        ("controladores", "mppt", []),
        ("controladores", "123", []),
    ],
)
def test_search_uses_documented_type_fields_only(
    catalog: Catalog,
    category: str,
    product_type: str,
    expected_names: list[str],
) -> None:
    """Type matching uses common fields and variant overrides, never free text."""
    results = catalog.search(categoria=category, tipo=product_type)

    assert [product.nombre_comercial for product in results] == expected_names


def test_search_combines_filters_on_the_same_variant(catalog: Catalog) -> None:
    """All variant-level filters must match one technically compatible variant."""
    matching = catalog.search(
        categoria="INVERSORES",
        fabricante="grow",
        capacidad_min=5000,
        capacidad_max=5000,
        tipo="conexion_a_red",
        modelo_contiene="grid",
    )
    incompatible_model = catalog.search(
        categoria="inversores",
        fabricante="Growatt",
        capacidad_min=5000,
        tipo="conexion_a_red",
        modelo_contiene="MIN",
    )

    assert matching == [catalog.products[1]]
    assert incompatible_model == []
