"""Catalog search module built on top of the S3 catalog index."""

import json
import logging
from json import JSONDecodeError
from typing import Any

from .s3_client import S3Client, S3DownloadError

logger = logging.getLogger(__name__)

CATALOG_INDEX_KEY = "index/catalog_index.json"
CAPACITY_FIELDS = ("capacidad_a", "potencia_w", "capacidad_wh")


class CatalogSearch:
    """Provide in-memory search capabilities over the catalog index."""

    def __init__(self, s3_client: S3Client | None = None) -> None:
        """Initialize CatalogSearch with the given S3 client.

        Args:
            s3_client: Optional S3 client instance for downloading the index.
        """

        self.s3_client = s3_client or S3Client()
        self._catalog_cache: dict[str, Any] | None = None

    def search(
        self,
        categoria: str,
        fabricante: str | None = None,
        capacidad_min: float | None = None,
        capacidad_max: float | None = None,
        tipo: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search products matching the provided filters.

        Args:
            categoria: Product category to match exactly.
            fabricante: Optional manufacturer filter (case-insensitive substring).
            capacidad_min: Optional minimum capacity threshold.
            capacidad_max: Optional maximum capacity threshold.
            tipo: Optional subtype filter checked against "tipo" and "subcategoria" fields.

        Returns:
            A list of product dictionaries that satisfy the filters.
        """

        catalog = self._load_catalog()
        productos = catalog.get("productos", [])
        if not isinstance(productos, list):
            logger.warning("Invalid catalog format: productos is not a list")
            return []

        resultados: list[dict[str, Any]] = []
        for producto in productos:
            if not self._matches_categoria(producto, categoria):
                continue

            if fabricante and not self._matches_fabricante(producto, fabricante):
                continue

            if tipo and not self._matches_tipo(producto, tipo):
                continue

            if not self._matches_capacidad(
                producto.get("variantes", []), capacidad_min, capacidad_max
            ):
                continue

            resultados.append(
                {
                    "id": producto.get("id"),
                    "nombre_comercial": producto.get("nombre_comercial"),
                    "categoria": producto.get("categoria"),
                    "fabricante": producto.get("fabricante"),
                    "ruta_s3": producto.get("ruta_s3"),
                    "subcategoria": producto.get("subcategoria"),
                    "variantes": producto.get("variantes", []),
                }
            )

        return resultados

    def _load_catalog(self) -> dict[str, Any]:
        """Load catalog_index.json from S3 when not cached."""

        if self._catalog_cache is not None:
            return self._catalog_cache

        try:
            catalog_bytes = self.s3_client.download_pdf(CATALOG_INDEX_KEY)
            catalog_str = catalog_bytes.decode("utf-8")
            catalog_data = json.loads(catalog_str)
            if not isinstance(catalog_data, dict):
                raise ValueError("Catalog index must be a JSON object")
            self._catalog_cache = catalog_data
        except (
            S3DownloadError,
            JSONDecodeError,
            UnicodeDecodeError,
            ValueError,
            KeyError,
        ) as exc:
            logger.warning("Failed to load catalog index: %s", exc)
            self._catalog_cache = {"productos": []}

        return self._catalog_cache

    @staticmethod
    def _matches_categoria(producto: dict[str, Any], categoria: str) -> bool:
        categoria_producto = producto.get("categoria")
        return categoria_producto == categoria

    @staticmethod
    def _matches_fabricante(producto: dict[str, Any], fabricante: str) -> bool:
        fabricante_producto = producto.get("fabricante", "")
        return fabricante.lower() in fabricante_producto.lower()

    @staticmethod
    def _matches_tipo(producto: dict[str, Any], tipo: str) -> bool:
        tipo_lower = tipo.lower()
        parametros_comunes = producto.get("parametros_comunes") or {}
        tipo_parametro = str(parametros_comunes.get("tipo", ""))
        subcategoria = str(producto.get("subcategoria", ""))
        return tipo_lower in tipo_parametro.lower() or tipo_lower in subcategoria.lower()

    @staticmethod
    def _matches_capacidad(
        variantes: list[dict[str, Any]],
        capacidad_min: float | None,
        capacidad_max: float | None,
    ) -> bool:
        if capacidad_min is None and capacidad_max is None:
            return True

        for variante in variantes:
            parametros = variante.get("parametros_clave", {})
            valor = CatalogSearch._extract_capacidad(parametros)
            if valor is None:
                continue

            if capacidad_min is not None and valor < capacidad_min:
                continue
            if capacidad_max is not None and valor > capacidad_max:
                continue

            return True

        return False

    @staticmethod
    def _extract_capacidad(parametros: dict[str, Any]) -> float | None:
        for field in CAPACITY_FIELDS:
            raw_value = parametros.get(field)
            if raw_value is None:
                continue
            try:
                return float(raw_value)
            except (TypeError, ValueError):
                continue
        return None
