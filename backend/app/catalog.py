"""
Catalog module for product indexing and search functionality.
Loads catalog index from S3 and provides search capabilities.
"""

import json
import logging
from typing import Any, List, Optional, Dict

from pydantic import BaseModel, Field

from backend.app.s3_client import S3Client, S3DownloadError

s3_client = S3Client()

logger = logging.getLogger(__name__)

CATALOG_INDEX_PATH = "index/catalog_index.json"


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
            products_data = index_data.get("products", [])
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

        if modelo_contiene:
            filtered = []
            for product in results:
                matching_variants = [
                    v
                    for v in product.variantes
                    if modelo_contiene.lower() in v.modelo.lower()
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


_catalog_instance: Optional[Catalog] = None


def get_catalog(force_reload: bool = False) -> Catalog:
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
            index_bytes = s3_client.download_pdf(CATALOG_INDEX_PATH)
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
