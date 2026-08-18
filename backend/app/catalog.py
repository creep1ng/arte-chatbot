"""
Catalog module for product indexing and search functionality.
Loads catalog index from S3 and provides search capabilities.
"""

import json
import logging
import math
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.s3_client import S3Client, S3DownloadError

s3_client = S3Client()

logger = logging.getLogger(__name__)

CATALOG_INDEX_PATH = "index/catalog_index.json"

CAPACITY_FIELD_BY_CATEGORY = {
    "paneles": "potencia_w",
    "inversores": "capacidad",
    "controladores": "capacidad_a",
    "baterias": "capacidad",
}

TYPE_FIELD_BY_CATEGORY = {
    "paneles": "tipo_celda",
    "inversores": "tipo",
    "controladores": "tipo",
    "baterias": "tipo",
}


def _normalize_numeric(value: Any) -> Optional[float]:
    """Return a finite float for a supported catalog numeric value."""
    if value is None or isinstance(value, bool):
        return None

    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None

    return normalized if math.isfinite(normalized) else None


class CatalogError(Exception):
    """Custom exception for catalog-related errors."""

    pass


class ProductVariant(BaseModel):
    """Variant of a product with specific parameters."""

    modelo: str
    parametros_clave: Dict[str, Any] = Field(default_factory=dict)


class CatalogProduct(BaseModel):
    """Product entry in the catalog index."""

    nombre_comercial: str
    fabricante: str
    categoria: str
    subcategoria: Optional[str] = None
    descripcion: Optional[str] = None
    ruta_s3: str
    variantes: List[ProductVariant] = Field(default_factory=list)
    parametros_comunes: Dict[str, Any] = Field(default_factory=dict)


class Catalog:
    """Catalog class that loads product index and provides search functionality."""

    def __init__(self, index_data: Dict[str, Any]):
        self.products: List[CatalogProduct] = []
        self._load_index(index_data)

    def _load_index(self, index_data: Dict[str, Any]) -> None:
        """Load and validate catalog index data."""
        try:
            products_data = index_data.get("productos", index_data.get("products", []))
            self.products = [CatalogProduct(**p) for p in products_data]
            logger.info("Loaded %d products into catalog", len(self.products))
        except Exception as e:
            logger.error("Failed to parse catalog index: %s", str(e))
            raise CatalogError(f"Invalid catalog index format: {e}") from e

    def search(
        self,
        categoria: Optional[str] = None,
        fabricante: Optional[str] = None,
        capacidad_min: Optional[float] = None,
        capacidad_max: Optional[float] = None,
        tipo: Optional[str] = None,
        modelo_contiene: Optional[str] = None,
    ) -> List[CatalogProduct]:
        """
        Search products in the catalog with optional filters.

        Args:
            categoria: Filter by product category (paneles, inversores, etc.)
            fabricante: Filter by manufacturer name
            capacidad_min: Minimum capacity filter
            capacidad_max: Maximum capacity filter
            tipo: Product type filter
            modelo_contiene: Filter variants containing this string in model name

        Returns:
            List of matching CatalogProduct objects
        """
        results = list(self.products)

        if categoria:
            results = [p for p in results if p.categoria.lower() == categoria.lower()]

        if fabricante:
            results = [p for p in results if fabricante.lower() in p.fabricante.lower()]

        if (
            modelo_contiene
            or capacidad_min is not None
            or capacidad_max is not None
            or tipo
        ):
            filtered = []
            for product in results:
                category = product.categoria.lower()
                capacity_field = CAPACITY_FIELD_BY_CATEGORY.get(category)
                type_field = TYPE_FIELD_BY_CATEGORY.get(category)
                matching_variants = [
                    v
                    for v in product.variantes
                    if (
                        not modelo_contiene
                        or modelo_contiene.lower() in v.modelo.lower()
                    )
                    and self._matches_capacity(
                        v,
                        capacity_field,
                        capacidad_min,
                        capacidad_max,
                    )
                    and self._matches_type(product, v, type_field, tipo)
                ]
                if matching_variants:
                    filtered.append(product)
            results = filtered

        logger.debug(
            "Catalog search returned %d results for filters: categoria=%s, fabricante=%s",
            len(results),
            categoria,
            fabricante,
        )

        return results

    @staticmethod
    def _matches_capacity(
        variant: ProductVariant,
        capacity_field: Optional[str],
        capacidad_min: Optional[float],
        capacidad_max: Optional[float],
    ) -> bool:
        """Return whether a variant satisfies inclusive capacity bounds."""
        if capacidad_min is None and capacidad_max is None:
            return True
        if capacity_field is None:
            return False

        capacity = _normalize_numeric(variant.parametros_clave.get(capacity_field))
        if capacity is None:
            return False
        if capacidad_min is not None and capacity < capacidad_min:
            return False
        if capacidad_max is not None and capacity > capacidad_max:
            return False
        return True

    @staticmethod
    def _matches_type(
        product: CatalogProduct,
        variant: ProductVariant,
        type_field: Optional[str],
        tipo: Optional[str],
    ) -> bool:
        """Return whether a variant matches its category's documented type field."""
        if not tipo:
            return True
        if type_field is None:
            return False

        product_type = variant.parametros_clave.get(
            type_field,
            product.parametros_comunes.get(type_field),
        )
        return isinstance(product_type, str) and (
            product_type.casefold() == tipo.casefold()
        )

    def contains_ruta_s3(self, ruta_s3: str) -> bool:
        """Return whether the S3 key is declared by the catalog."""
        return any(product.ruta_s3 == ruta_s3 for product in self.products)


_catalog_instance: Optional[Catalog] = None


def get_catalog(
    force_reload: bool = False, timeout_seconds: Optional[float] = None
) -> Catalog:
    """
    Get the singleton catalog instance. Loads from S3 if not already loaded.

    Args:
        force_reload: If True, reload catalog from S3 even if already loaded

    Returns:
        Initialized Catalog instance

    Raises:
        CatalogError: If catalog cannot be loaded from S3
    """
    global _catalog_instance

    if _catalog_instance is None or force_reload:
        logger.info("Loading catalog index from S3: %s", CATALOG_INDEX_PATH)
        try:
            index_bytes = s3_client.download_pdf(
                CATALOG_INDEX_PATH, timeout_seconds=timeout_seconds
            )
            index_data = json.loads(index_bytes.decode("utf-8"))
            _catalog_instance = Catalog(index_data)
        except S3DownloadError as e:
            logger.error("Failed to download catalog index from S3: %s", str(e))
            raise CatalogError(f"Could not retrieve catalog index: {e}") from e
        except json.JSONDecodeError as e:
            logger.error("Failed to parse catalog index JSON: %s", str(e))
            raise CatalogError(f"Invalid catalog index JSON: {e}") from e
        except Exception as e:
            logger.exception("Unexpected error loading catalog")
            raise CatalogError(f"Failed to load catalog: {e}") from e

    return _catalog_instance
