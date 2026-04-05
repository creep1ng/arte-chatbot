"""Catalog module for searching products in catalog_index.json.

This module provides functionality to search products in the catalog
using various criteria like category, manufacturer, model, and capacity.
"""

import json
import logging
from typing import Any, Optional

from backend.app.config import settings
from backend.app.s3_client import S3Client, S3DownloadError

logger = logging.getLogger(__name__)

# S3 key for the catalog index
CATALOG_INDEX_S3_KEY = "index/catalog_index.json"


class CatalogError(Exception):
    """Raised when catalog operations fail."""

    pass


class CatalogSearchResult:
    """Represents a product search result with its variants and S3 route."""

    def __init__(
        self,
        id: str,
        nombre_comercial: str,
        categoria: str,
        fabricante: str,
        ruta_s3: str,
        descripcion: Optional[str] = None,
        variantes: Optional[list[dict[str, Any]]] = None,
        parametros_comunes: Optional[dict[str, Any]] = None,
    ) -> None:
        self.id = id
        self.nombre_comercial = nombre_comercial
        self.categoria = categoria
        self.fabricante = fabricante
        self.ruta_s3 = ruta_s3
        self.descripcion = descripcion
        self.variantes = variantes or []
        self.parametros_comunes = parametros_comunes or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for tool response."""
        return {
            "id": self.id,
            "nombre_comercial": self.nombre_comercial,
            "categoria": self.categoria,
            "fabricante": self.fabricante,
            "ruta_s3": self.ruta_s3,
            "descripcion": self.descripcion,
            "variantes": self.variantes,
        }

    @classmethod
    def from_product_dict(cls, product: dict[str, Any]) -> "CatalogSearchResult":
        """Create from a product dictionary in catalog_index format."""
        return cls(
            id=product.get("id", ""),
            nombre_comercial=product.get("nombre_comercial", ""),
            categoria=product.get("categoria", ""),
            fabricante=product.get("fabricante", ""),
            ruta_s3=product.get("ruta_s3", ""),
            descripcion=product.get("descripcion"),
            variantes=product.get("variantes", []),
            parametros_comunes=product.get("parametros_comunes", {}),
        )


class Catalog:
    """Client for searching products in the catalog index."""

    def __init__(self, s3_client: Optional[S3Client] = None) -> None:
        """Initialize the catalog client.

        Args:
            s3_client: Optional S3Client instance. If not provided,
                       a new one will be created.
        """
        self._s3_client = s3_client or S3Client()
        self._index_cache: Optional[dict[str, Any]] = None

    def _load_index(self) -> dict[str, Any]:
        """Load the catalog index from S3 or cache.

        Returns:
            The catalog index dictionary.

        Raises:
            CatalogError: If the index cannot be loaded.
        """
        if self._index_cache is not None:
            return self._index_cache

        try:
            logger.debug("Loading catalog index from S3: %s", CATALOG_INDEX_S3_KEY)
            index_bytes = self._s3_client.download_pdf(CATALOG_INDEX_S3_KEY)
            index_data: dict[str, Any] = json.loads(index_bytes.decode("utf-8"))
            self._index_cache = index_data
            productos = index_data.get("productos", [])
            logger.info(
                "Catalog index loaded: %d products",
                len(productos),
            )
            return index_data
        except S3DownloadError as e:
            logger.error("Failed to load catalog index: %s", e)
            raise CatalogError(f"Failed to load catalog index: {e}") from e
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in catalog index: %s", e)
            raise CatalogError(f"Invalid catalog index JSON: {e}") from e

    def invalidate_cache(self) -> None:
        """Invalidate the cached catalog index."""
        self._index_cache = None
        logger.debug("Catalog index cache invalidated")

    def search(
        self,
        categoria: str,
        fabricante: Optional[str] = None,
        capacidad_min: Optional[float] = None,
        capacidad_max: Optional[float] = None,
        tipo: Optional[str] = None,
        modelo_contiene: Optional[str] = None,
    ) -> list[CatalogSearchResult]:
        """Search for products in the catalog.

        Args:
            categoria: Product category (paneles, inversores, controladores, baterias).
            fabricante: Optional manufacturer name to filter by.
            capacidad_min: Optional minimum capacity (W for panels/inverters, Ah for batteries).
            capacidad_max: Optional maximum capacity.
            tipo: Optional product type (e.g., mppt, pwm, monocristalino, multifuncional).
            modelo_contiene: Optional string that the model name should contain.

        Returns:
            List of matching products with their variants.
        """
        index = self._load_index()
        productos = index.get("productos", [])
        resultados: list[CatalogSearchResult] = []

        logger.debug(
            "Searching catalog: categoria=%s, fabricante=%s, capacidad_min=%s, "
            "capacidad_max=%s, tipo=%s, modelo_contiene=%s",
            categoria,
            fabricante,
            capacidad_min,
            capacidad_max,
            tipo,
            modelo_contiene,
        )

        for producto in productos:
            # Filter by category
            if producto.get("categoria") != categoria:
                continue

            # Filter by manufacturer (case-insensitive partial match)
            if fabricante:
                fabricante_producto = producto.get("fabricante", "").lower()
                if fabricante.lower() not in fabricante_producto:
                    continue

            # Filter by type in parametros_comunes
            if tipo:
                parametros_comunes = producto.get("parametros_comunes", {})
                tipo_producto = str(parametros_comunes.get("tipo", "")).lower()
                if tipo.lower() not in tipo_producto:
                    continue

            # Filter variantes by capacity and model name
            variantes = producto.get("variantes", [])
            variantes_filtradas: list[dict[str, Any]] = []

            for variante in variantes:
                parametros_clave = variante.get("parametros_clave", {})

                # Check capacity range
                if capacidad_min is not None or capacidad_max is not None:
                    capacidad = self._get_capacidad(parametros_clave, producto)
                    if capacidad is None:
                        # If no capacidad found, include the variant but won't filter by capacity
                        pass
                    else:
                        if capacidad_min is not None and capacidad < capacidad_min:
                            continue
                        if capacidad_max is not None and capacidad > capacidad_max:
                            continue

                # Check model name contains
                if modelo_contiene:
                    modelo = variante.get("modelo", "").lower()
                    if modelo_contiene.lower() not in modelo:
                        continue

                variantes_filtradas.append(variante)

            # Only include product if it has matching variants
            if variantes_filtradas:
                result = CatalogSearchResult.from_product_dict(producto)
                result.variantes = variantes_filtradas
                resultados.append(result)

        logger.info(
            "Catalog search found %d products with %d total variants",
            len(resultados),
            sum(len(r.variantes) for r in resultados),
        )
        return resultados

    def _get_capacidad(
        self, parametros_clave: dict[str, Any], producto: dict[str, Any]
    ) -> Optional[float]:
        """Extract capacity value from variant parameters.

        The capacity field name varies by category:
        - paneles: potencia_w (in W)
        - inversores: capacidad (in W or kVA)
        - controladores: capacidad_a (in A)
        - baterias: capacidad (in Ah or kWh)

        Args:
            parametros_clave: The variant's parametros_clave dictionary.
            producto: The full product dictionary for fallback.

        Returns:
            The capacity value or None if not found.
        """
        # Try variant-level capacity
        if "potencia_w" in parametros_clave:
            return float(parametros_clave["potencia_w"])
        if "capacidad" in parametros_clave:
            return float(parametros_clave["capacidad"])
        if "capacidad_a" in parametros_clave:
            return float(parametros_clave["capacidad_a"])

        # Fall back to parametros_comunes
        parametros_comunes = producto.get("parametros_comunes", {})
        if "potencia_w" in parametros_comunes:
            return float(parametros_comunes["potencia_w"])
        if "capacidad" in parametros_comunes:
            return float(parametros_comunes["capacidad"])
        if "capacidad_a" in parametros_comunes:
            return float(parametros_comunes["capacidad_a"])

        return None

    def get_product_by_ruta_s3(self, ruta_s3: str) -> Optional[CatalogSearchResult]:
        """Get a product by its S3 route.

        Args:
            ruta_s3: The S3 path to the product's PDF.

        Returns:
            The product if found, None otherwise.
        """
        index = self._load_index()
        productos = index.get("productos", [])

        for producto in productos:
            if producto.get("ruta_s3") == ruta_s3:
                return CatalogSearchResult.from_product_dict(producto)

        return None


# Global catalog instance
_catalog: Optional[Catalog] = None


def get_catalog() -> Catalog:
    """Get the global Catalog instance.

    Returns:
        The Catalog singleton.
    """
    global _catalog
    if _catalog is None:
        _catalog = Catalog()
    return _catalog


# Module-level function for backward compatibility
def search_products(
    categoria: str,
    fabricante: Optional[str] = None,
    capacidad_min: Optional[float] = None,
    capacidad_max: Optional[float] = None,
    tipo: Optional[str] = None,
    modelo_contiene: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Search for products and return as list of dictionaries.

    This is a convenience function that wraps Catalog.search().

    Args:
        categoria: Product category.
        fabricante: Optional manufacturer name.
        capacidad_min: Optional minimum capacity.
        capacidad_max: Optional maximum capacity.
        tipo: Optional product type.
        modelo_contiene: Optional model name substring.

    Returns:
        List of product dictionaries.
    """
    results = get_catalog().search(
        categoria=categoria,
        fabricante=fabricante,
        capacidad_min=capacidad_min,
        capacidad_max=capacidad_max,
        tipo=tipo,
        modelo_contiene=modelo_contiene,
    )
    return [r.to_dict() for r in results]
