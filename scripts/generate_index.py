#!/usr/bin/env python3
"""
Generate Catalog Index Script (AI-Powered)

Generates catalog_index.json by reading PDFs from S3, extracting metadata
via OpenAI File Inputs, and producing a schema-validated JSON index.

Usage:
    python generate_index.py                         # Use S3 defaults
    python generate_index.py --local-only            # Save locally, skip S3 upload
    python generate_index.py --batch-size 10         # 10 PDFs per LLM call (max)
    python generate_index.py --force                 # Reprocess all PDFs
    python generate_index.py --dry-run               # Preview without writing
    python generate_index.py --source-dir ./data     # Local development mode

The script is idempotent: it skips PDFs already present in the existing index
unless --force is specified.
"""

import argparse
import io
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BUCKET = "arte-chatbot-data"
DEFAULT_PREFIX = "raw/"
DEFAULT_INDEX_S3_KEY = "index/catalog_index.json"
DEFAULT_OUTPUT_LOCAL = "backend/config/catalog_index.json"
DEFAULT_SCHEMA_PATH = "docs/schemas/catalog_index.schema.json"
DEFAULT_BATCH_SIZE = 5
MAX_BATCH_SIZE = 10
INDEX_VERSION = "1.1.0"
SUPPORTED_EXTENSIONS = {".pdf", ".PDF"}

# Valid top-level categories
VALID_CATEGORIES = {"paneles", "inversores", "controladores", "baterias"}

# ---------------------------------------------------------------------------
# System prompt for AI extraction
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """Eres un asistente especializado en extraer metadatos estructurados
de fichas técnicas de productos de energía solar (paneles, inversores, controladores, baterías).

Tu tarea es analizar cada ficha técnica PDF adjunta y generar un objeto JSON por cada una,
siguiendo estrictamente el schema proporcionado.

## Schema de referencia

Cada producto debe tener la siguiente estructura:
{
  "nombre_comercial": "string - Nombre de la serie o línea de productos",
  "fabricante": "string - Marca o fabricante",
  "descripcion": "string - Descripción breve (opcional)",
  "url_fabricante": "string - URL oficial (opcional)",
  "version_ficha": "string - Versión de la ficha técnica (opcional)",
  "parametros_comunes": { ... } - Parámetros técnicos compartidos por todas las variantes,
  "variantes": [
    {
      "modelo": "string - Nombre del modelo específico",
      "parametros_clave": { ... } - Solo los parámetros que difieren entre variantes
    }
  ]
}

## Parámetros por categoría

### Paneles (categoria: "paneles")
- parametros_comunes: { "tipo_celda": "monocristalino" | "policristalino" }
- parametros_clave: { "potencia_w": number }

### Inversores (categoria: "inversores")
- parametros_comunes: { "tipo": "onda_pura"|"onda_modificada"|"multifuncional"|"hibrido"|"conexion_a_red" }
  - Si tipo es onda_pura/onda_modificada/multifuncional: agregar "nivel_tension": number
  - Si tipo es hibrido/conexion_a_red: agregar "fases": "bifasico"|"trifasico"
- parametros_clave: { "capacidad": number } (en Watts)

### Controladores (categoria: "controladores")
- parametros_comunes: { "tipo": "mppt"|"pwm", "tension_v": number }
- parametros_clave: { "capacidad_a": number } (en Amperios)

### Baterías (categoria: "baterias")
- parametros_comunes: { "tipo": "Gel"|"Litio" }
  - Si tipo es "Litio": agregar "nivel_tension": number
- parametros_clave: { "capacidad": number } (en Ah o kWh)

## Reglas importantes
1. Extrae SOLO datos presentes en la ficha técnica. No inventes valores.
2. Si un dato no está disponible, omite el campo (no pongas null).
3. Los valores numéricos deben ser números, no strings.
4. nombre_comercial debe ser el nombre de la serie/línea, NO un modelo individual.
5. variantes debe contener TODOS los modelos listados en la ficha técnica.
6. Si la ficha cubre una sola variante, igual debe haber un array con un elemento.
7. Asegúrate siempre incluir la marca del equipo. Suelen estar en los encabezados (parte superior) de las fichas técnicas.

Responde ÚNICAMENTE con un objeto JSON válido con la clave "productos" que contenga un array."""


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------


class S3Manager:
    """Manages S3 operations for the index generation pipeline."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_region: Optional[str] = None,
    ) -> None:
        self.bucket_name = bucket_name or os.getenv("AWS_BUCKET_NAME", DEFAULT_BUCKET)
        self.aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = aws_secret_access_key or os.getenv(
            "AWS_SECRET_ACCESS_KEY"
        )
        self.aws_region = aws_region or os.getenv("AWS_REGION", "us-east-1")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
            )
        return self._client

    def list_pdfs(self, prefix: str = DEFAULT_PREFIX) -> list[dict[str, Any]]:
        """List all PDF files under the given prefix, recursively.

        Returns:
            List of dicts with keys: s3_key, filename, categoria, subcategoria, nombre_comercial.
        """
        pdfs: list[dict[str, Any]] = []
        paginator = self.client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if any(key.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                    parsed = _parse_s3_key(key, prefix)
                    if parsed:
                        pdfs.append(parsed)

        # Sort by s3_key for deterministic ordering
        pdfs.sort(key=lambda p: str(p.get("s3_key", "")))
        return pdfs

    def download_pdf(self, s3_key: str) -> bytes:
        """Download a PDF file from S3."""
        response = self.client.get_object(Bucket=self.bucket_name, Key=s3_key)
        return response["Body"].read()

    def upload_json(self, data: dict[str, Any], s3_key: str) -> None:
        """Upload a JSON object to S3."""
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=body,
            ContentType="application/json",
        )

    def download_json(self, s3_key: str) -> Optional[dict[str, Any]]:
        """Download and parse a JSON file from S3. Returns None if not found."""
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=s3_key)
            return json.loads(response["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                return None
            raise


# ---------------------------------------------------------------------------
# Local file helpers
# ---------------------------------------------------------------------------


def list_local_pdfs(source_dir: str) -> list[dict[str, Any]]:
    """List PDF files from a local directory, preserving the two-level structure.

    The directory structure should mirror the S3 layout:
        source_dir/{categoria}/[{subcategoria}/]{nombre_comercial}.pdf

    Results are sorted by s3_key for deterministic ordering.
    """
    dir_path = Path(source_dir)
    if not dir_path.exists():
        logger.warning("Source directory '%s' does not exist.", source_dir)
        return []

    # Collect all files first, then sort for determinism
    all_files = sorted(
        (
            f
            for f in dir_path.rglob("*")
            if f.is_file() and f.suffix in SUPPORTED_EXTENSIONS
        ),
        key=lambda f: str(f.relative_to(dir_path)),
    )

    pdfs: list[dict[str, Any]] = []
    for file_path in all_files:
        # Compute relative path from source_dir
        rel_path = file_path.relative_to(dir_path)
        parts = list(rel_path.parts)
        filename = file_path.stem

        categoria: str = ""
        subcategoria: Optional[str] = None

        if len(parts) == 2:
            # {categoria}/{filename}.pdf
            categoria = parts[0]
        elif len(parts) >= 3:
            # {categoria}/{subcategoria}/{filename}.pdf (or deeper)
            categoria = parts[0]
            subcategoria = parts[1]

        pdfs.append(
            {
                "s3_key": str(rel_path).replace("\\", "/"),
                "filename": filename,
                "categoria": categoria,
                "subcategoria": subcategoria,
                "nombre_comercial": filename,
            }
        )

    return pdfs


def download_local_pdf(source_dir: str, relative_path: str) -> bytes:
    """Read a PDF file from local directory."""
    full_path = Path(source_dir) / relative_path
    return full_path.read_bytes()


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_s3_key(s3_key: str, prefix: str) -> Optional[dict[str, Optional[str]]]:
    """Parse an S3 key to extract categoria, subcategoria, and nombre_comercial.

    Expected formats:
        raw/{categoria}/{nombre_comercial}.pdf
        raw/{categoria}/{subcategoria}/{nombre_comercial}.pdf

    Returns None if the key doesn't match expected patterns.
    """
    # Remove prefix to get relative path
    if s3_key.startswith(prefix):
        rel_path = s3_key[len(prefix) :]
    else:
        rel_path = s3_key

    parts = rel_path.split("/")
    # Filter out empty parts
    parts = [p for p in parts if p]

    if len(parts) < 2:
        # At minimum: {categoria}/{file}.pdf
        return None

    filename = Path(parts[-1]).stem  # Remove .pdf extension

    if len(parts) == 2:
        # {categoria}/{file}.pdf
        return {
            "s3_key": s3_key,
            "filename": filename,
            "categoria": parts[0],
            "subcategoria": None,
            "nombre_comercial": filename,
        }
    elif len(parts) >= 3:
        # {categoria}/{subcategoria}/{file}.pdf
        return {
            "s3_key": s3_key,
            "filename": filename,
            "categoria": parts[0],
            "subcategoria": parts[1],
            "nombre_comercial": filename,
        }

    return None


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug (lowercase, hyphens)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


# ---------------------------------------------------------------------------
# Idempotency: filter already-processed PDFs
# ---------------------------------------------------------------------------


def filter_new_pdfs(
    pdfs: list[dict[str, Any]],
    existing_index: Optional[dict[str, Any]],
    prefix: str = DEFAULT_PREFIX,
) -> list[dict[str, Any]]:
    """Filter out PDFs that are already present in the existing index.

    Matching is done by normalized ruta_s3. The prefix is stripped from both
    sides to handle S3 paths (raw/...) and local paths (...) consistently.
    """
    if existing_index is None:
        return pdfs

    def _normalize(path: str) -> str:
        """Strip prefix and trailing/leading slashes for comparison."""
        if path.startswith(prefix):
            path = path[len(prefix) :]
        return path.strip("/")

    existing_keys: set[str] = set()
    for producto in existing_index.get("productos", []):
        ruta = producto.get("ruta_s3", "")
        if ruta:
            existing_keys.add(_normalize(ruta))

    return [
        p for p in pdfs if _normalize(str(p.get("s3_key", ""))) not in existing_keys
    ]


# ---------------------------------------------------------------------------
# AI extraction
# ---------------------------------------------------------------------------


def extract_metadata_batch(
    pdf_bytes_list: list[tuple[str, bytes, dict[str, str]]],
    api_key: str,
    model: str = "gpt-4o",
) -> list[dict[str, Any]]:
    """Extract metadata from a batch of PDFs using OpenAI File Inputs.

    Args:
        pdf_bytes_list: List of (s3_key, pdf_bytes, pdf_info) tuples.
        api_key: OpenAI API key.
        model: Model to use for extraction.

    Returns:
        List of extracted product metadata dicts.
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    file_ids: list[str] = []
    s3_key_map: dict[str, str] = {}  # file_id -> s3_key

    try:
        # Upload PDFs to OpenAI Files API
        for s3_key, pdf_bytes, pdf_info in pdf_bytes_list:
            file_obj = io.BytesIO(pdf_bytes)
            file_obj.name = pdf_info.get("nombre_comercial", "document") + ".pdf"

            response = client.files.create(file=file_obj, purpose="user_data")
            file_ids.append(response.id)
            s3_key_map[response.id] = s3_key

        # Build the user message with file references
        user_message_parts = [
            "Analiza las siguientes fichas técnicas PDF y extrae los metadatos "
            "estructurados según el schema proporcionado en el system prompt.\n"
        ]

        for file_id, s3_key in s3_key_map.items():
            pdf_info = next((p for p in pdf_bytes_list if p[0] == s3_key), None)
            if pdf_info:
                info = pdf_info[2]
                user_message_parts.append(
                    f"- File ID: {file_id}\n"
                    f"  Categoría: {info['categoria']}\n"
                    f"  Subcategoría: {info.get('subcategoria') or 'N/A'}\n"
                    f"  Nombre comercial (del archivo): {info['nombre_comercial']}"
                )

        user_message = "\n".join(user_message_parts)

        # Build content list with file references
        content: list[dict[str, Any]] = [{"type": "text", "text": user_message}]

        # Call the LLM
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        result_text = response.choices[0].message.content
        result = json.loads(result_text)

        return result.get("productos", [])

    finally:
        # Cleanup: delete uploaded files from OpenAI
        for file_id in file_ids:
            try:
                client.files.delete(file_id)
                logger.debug("Deleted OpenAI file: %s", file_id)
            except Exception as e:
                logger.warning("Failed to delete OpenAI file %s: %s", file_id, e)


# ---------------------------------------------------------------------------
# Build final catalog index
# ---------------------------------------------------------------------------


def build_product_entry(
    extracted: dict[str, Any],
    pdf_info: dict[str, str],
) -> dict[str, Any]:
    """Build a complete product entry combining extracted metadata and S3 info.

    Args:
        extracted: Metadata extracted by the LLM.
        pdf_info: Info from S3 discovery (s3_key, categoria, subcategoria, etc.).

    Returns:
        A product dict conforming to the catalog_index schema.
    """
    nombre_comercial = extracted.get("nombre_comercial", pdf_info["nombre_comercial"])
    producto_id = _slugify(nombre_comercial)

    entry: dict[str, Any] = {
        "id": producto_id,
        "nombre_comercial": nombre_comercial,
        "categoria": pdf_info["categoria"],
        "fabricante": extracted.get("fabricante", "Desconocido"),
        "ruta_s3": pdf_info["s3_key"],
        "fecha_ingesta": datetime.now(timezone.utc).isoformat(),
    }

    # Add optional fields
    if pdf_info.get("subcategoria"):
        entry["subcategoria"] = pdf_info["subcategoria"]

    if extracted.get("descripcion"):
        entry["descripcion"] = extracted["descripcion"]

    if extracted.get("url_fabricante"):
        entry["url_fabricante"] = extracted["url_fabricante"]

    if extracted.get("version_ficha"):
        entry["version_ficha"] = extracted["version_ficha"]

    # Add parametros_comunes
    if extracted.get("parametros_comunes"):
        entry["parametros_comunes"] = extracted["parametros_comunes"]

    # Add variantes
    entry["variantes"] = extracted.get("variantes", [])

    return entry


def build_catalog_index(
    products: list[dict[str, Any]],
    existing_index: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build the final catalog index, merging with existing if present.

    Args:
        products: New product entries to add.
        existing_index: Existing catalog_index.json to merge with.

    Returns:
        Complete catalog index dict.
    """
    all_products: list[dict[str, Any]] = []

    # Start with existing products
    if existing_index:
        all_products.extend(existing_index.get("productos", []))

    # Add new products
    all_products.extend(products)

    # Sort for determinism
    all_products.sort(
        key=lambda p: (p.get("categoria", ""), p.get("nombre_comercial", ""))
    )

    return {
        "version": INDEX_VERSION,
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "generado_por": "ai-pipeline",
        "productos": all_products,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_index(
    catalog: dict[str, Any],
    schema_path: str,
) -> list[str]:
    """Validate the catalog index against the JSON schema.

    Returns:
        List of validation error messages (empty if valid).
    """
    try:
        import jsonschema
    except ImportError:
        logger.warning("jsonschema not installed, skipping validation")
        return []

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except FileNotFoundError:
        logger.warning("Schema file not found: %s", schema_path)
        return [f"Schema file not found: {schema_path}"]

    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for error in validator.iter_errors(catalog):
        path = " -> ".join(str(p) for p in error.absolute_path)
        errors.append(f"{path}: {error.message}")

    return errors


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_local(catalog: dict[str, Any], output_path: str) -> None:
    """Save catalog index to local JSON file."""
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    logger.info("Catalog index saved locally: %s", output_path)
    logger.info("Total products: %d", len(catalog.get("productos", [])))


def upload_to_s3(
    catalog: dict[str, Any],
    s3_manager: S3Manager,
    s3_key: str,
) -> None:
    """Upload catalog index to S3."""
    s3_manager.upload_json(catalog, s3_key)
    logger.info(
        "Catalog index uploaded to S3: s3://%s/%s",
        s3_manager.bucket_name,
        s3_key,
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_pipeline(
    s3_manager: Optional[S3Manager],
    source_dir: Optional[str],
    prefix: str,
    output_path: str,
    index_s3_key: str,
    schema_path: str,
    batch_size: int,
    local_only: bool,
    dry_run: bool,
    force: bool,
    api_key: str,
    model: str,
) -> int:
    """Execute the full index generation pipeline.

    Returns:
        Exit code (0 = success).
    """
    # Step 1: Discover PDFs
    logger.info("Step 1: Discovering PDFs...")

    if source_dir:
        pdfs = list_local_pdfs(source_dir)
        logger.info("Found %d PDFs in local directory: %s", len(pdfs), source_dir)
    elif s3_manager:
        pdfs = s3_manager.list_pdfs(prefix)
        logger.info(
            "Found %d PDFs in S3 bucket: %s/%s",
            len(pdfs),
            s3_manager.bucket_name,
            prefix,
        )
    else:
        logger.error("No source specified (neither S3 nor local directory)")
        return 1

    if not pdfs:
        logger.warning("No PDF files found. Nothing to process.")
        # Still generate empty index for idempotency
        catalog = build_catalog_index([], None)
        if not dry_run:
            save_local(catalog, output_path)
            if not local_only and s3_manager:
                upload_to_s3(catalog, s3_manager, index_s3_key)
        else:
            print(json.dumps(catalog, indent=2, ensure_ascii=False))
        return 0

    # Step 2: Load existing index (from S3 or local)
    logger.info("Step 2: Loading existing index...")
    existing_index: Optional[dict[str, Any]] = None

    if not force:
        if s3_manager and not source_dir:
            existing_index = s3_manager.download_json(index_s3_key)
            if existing_index:
                logger.info(
                    "Loaded existing index from S3 with %d products",
                    len(existing_index.get("productos", [])),
                )

        # Also try local
        if existing_index is None and os.path.exists(output_path):
            with open(output_path, "r", encoding="utf-8") as f:
                existing_index = json.load(f)
            if existing_index:
                logger.info(
                    "Loaded existing index from local with %d products",
                    len(existing_index.get("productos", [])),
                )

    # Step 3: Filter already-processed PDFs
    if force:
        new_pdfs = pdfs
        logger.info("Step 3: Force mode - processing all %d PDFs", len(pdfs))
    else:
        new_pdfs = filter_new_pdfs(pdfs, existing_index, prefix)
        logger.info(
            "Step 3: %d new PDFs to process (skipped %d already indexed)",
            len(new_pdfs),
            len(pdfs) - len(new_pdfs),
        )

    if not new_pdfs:
        logger.info("No new PDFs to process. Index is up to date.")
        # Save existing index to ensure consistency
        if existing_index and not dry_run:
            save_local(existing_index, output_path)
            if not local_only and s3_manager:
                upload_to_s3(existing_index, s3_manager, index_s3_key)
        return 0

    # Step 4: Batch and extract metadata with AI
    logger.info("Step 4: Extracting metadata with AI (batch size: %d)...", batch_size)

    all_extracted: list[dict[str, Any]] = []

    for i in range(0, len(new_pdfs), batch_size):
        batch = new_pdfs[i : i + batch_size]
        logger.info(
            "Processing batch %d/%d (%d PDFs)...",
            (i // batch_size) + 1,
            (len(new_pdfs) + batch_size - 1) // batch_size,
            len(batch),
        )

        # Download PDFs for this batch
        pdf_bytes_list: list[tuple[str, bytes, dict[str, str]]] = []
        for pdf_info in batch:
            try:
                if source_dir:
                    pdf_bytes = download_local_pdf(source_dir, pdf_info["s3_key"])
                elif s3_manager:
                    pdf_bytes = s3_manager.download_pdf(pdf_info["s3_key"])
                else:
                    continue

                pdf_bytes_list.append((pdf_info["s3_key"], pdf_bytes, pdf_info))
            except Exception as e:
                logger.error(
                    "Failed to download %s: %s. Skipping.",
                    pdf_info["s3_key"],
                    e,
                )

        if not pdf_bytes_list:
            continue

        if dry_run:
            logger.info("[DRY RUN] Would process %d PDFs with AI", len(pdf_bytes_list))
            for _, _, info in pdf_bytes_list:
                all_extracted.append(
                    build_product_entry(
                        {"nombre_comercial": info["nombre_comercial"], "variantes": []},
                        info,
                    )
                )
        else:
            try:
                extracted = extract_metadata_batch(pdf_bytes_list, api_key, model)
                for ext_product, (_, _, pdf_info) in zip(extracted, pdf_bytes_list):
                    entry = build_product_entry(ext_product, pdf_info)
                    all_extracted.append(entry)
            except Exception as e:
                logger.error("AI extraction failed for batch: %s", e)
                logger.info("Falling back to basic entry creation for this batch")
                for _, _, info in pdf_bytes_list:
                    all_extracted.append(
                        build_product_entry(
                            {
                                "nombre_comercial": info["nombre_comercial"],
                                "variantes": [],
                            },
                            info,
                        )
                    )

    logger.info("Extracted metadata for %d products", len(all_extracted))

    # Step 5: Build final catalog index
    logger.info("Step 5: Building catalog index...")
    catalog = build_catalog_index(all_extracted, existing_index)

    # Step 6: Validate
    logger.info("Step 6: Validating against schema...")
    validation_errors = validate_index(catalog, schema_path)
    if validation_errors:
        logger.warning("Schema validation errors found:")
        for err in validation_errors:
            logger.warning("  - %s", err)
        logger.warning("Proceeding despite validation errors (review output manually)")
    else:
        logger.info("Schema validation passed")

    # Step 7: Save
    if dry_run:
        logger.info("[DRY RUN] Would save catalog index")
        print(json.dumps(catalog, indent=2, ensure_ascii=False))
    else:
        logger.info("Step 7: Saving catalog index...")
        save_local(catalog, output_path)

        if not local_only and s3_manager:
            try:
                upload_to_s3(catalog, s3_manager, index_s3_key)
            except Exception as e:
                logger.error(
                    "Failed to upload to S3: %s. Local copy saved at: %s",
                    e,
                    output_path,
                )

    logger.info(
        "Pipeline complete. Total products in index: %d",
        len(catalog.get("productos", [])),
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate catalog index from PDFs using AI extraction.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        default=None,
        help="Local directory containing PDFs (mirrors S3 structure).",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default=None,
        help="S3 bucket name (default: AWS_BUCKET_NAME env var or arte-chatbot-data).",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default=DEFAULT_PREFIX,
        help=f"S3 prefix for PDF discovery (default: {DEFAULT_PREFIX}).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"PDFs per LLM call, 1-{MAX_BATCH_SIZE} (default: {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_LOCAL,
        help=f"Local output path for catalog_index.json (default: {DEFAULT_OUTPUT_LOCAL}).",
    )
    parser.add_argument(
        "--index-s3-key",
        type=str,
        default=DEFAULT_INDEX_S3_KEY,
        help=f"S3 key for the index file (default: {DEFAULT_INDEX_S3_KEY}).",
    )
    parser.add_argument(
        "--schema",
        type=str,
        default=DEFAULT_SCHEMA_PATH,
        help=f"Path to JSON schema for validation (default: {DEFAULT_SCHEMA_PATH}).",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Save locally only, do not upload to S3.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without writing files or calling AI.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess all PDFs, ignoring existing index.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="OpenAI model to use for extraction (default: gpt-4o).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Validate batch size
    batch_size = max(1, min(args.batch_size, MAX_BATCH_SIZE))
    if batch_size != args.batch_size:
        logger.warning(
            "Batch size clamped to %d (requested: %d)", batch_size, args.batch_size
        )

    # Get API key
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key and not args.dry_run:
        logger.error(
            "OPENAI_API_KEY not set. Set it via environment variable or use --dry-run."
        )
        return 1

    # Initialize S3 manager (skip if using local source)
    s3_manager: Optional[S3Manager] = None
    if not args.source_dir:
        try:
            s3_manager = S3Manager(bucket_name=args.bucket)
            # Quick connectivity check
            s3_manager.client.list_objects_v2(Bucket=s3_manager.bucket_name, MaxKeys=1)
            logger.info("Connected to S3 bucket: %s", s3_manager.bucket_name)
        except (NoCredentialsError, ClientError) as e:
            if args.local_only or args.source_dir:
                logger.warning("S3 not available: %s. Running in local-only mode.", e)
                s3_manager = None
            else:
                logger.error(
                    "S3 connection failed: %s. Use --source-dir for local mode.", e
                )
                return 1

    return run_pipeline(
        s3_manager=s3_manager,
        source_dir=args.source_dir,
        prefix=args.prefix,
        output_path=args.output,
        index_s3_key=args.index_s3_key,
        schema_path=args.schema,
        batch_size=batch_size,
        local_only=args.local_only,
        dry_run=args.dry_run,
        force=args.force,
        api_key=api_key,
        model=args.model,
    )


if __name__ == "__main__":
    sys.exit(main())
