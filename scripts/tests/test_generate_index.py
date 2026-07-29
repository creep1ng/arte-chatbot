"""Tests for generate_index.py — AI-powered catalog index generation pipeline."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

# Add scripts directory to path for import
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from generate_index import (
    DocumentExtraction,
    ExtractedProduct,
    ExtractionBatch,
    ExtractionNeedsReview,
    ExtractionProtocolError,
    ExtractionStatus,
    MAX_BATCH_SIZE,
    TrustedDocument,
    _parse_s3_key,
    _slugify,
    build_catalog_index,
    build_product_entry,
    build_trusted_map,
    filter_new_pdfs,
    list_local_pdfs,
    reconcile_batch,
    save_local,
    validate_index,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_extracted_panel() -> dict[str, Any]:
    """Sample LLM-extracted metadata for a panel."""
    return {
        "nombre_comercial": "Jinko Tiger Pro",
        "fabricante": "Jinko",
        "descripcion": "Módulo fotovoltaico monocristalino de alta eficiencia.",
        "url_fabricante": "https://www.jinkosolar.com/tiger-pro",
        "parametros_comunes": {
            "tipo_celda": "monocristalino",
        },
        "variantes": [
            {
                "modelo": "Tiger Pro 460W",
                "parametros_clave": {"potencia_w": 460},
            },
            {
                "modelo": "Tiger Pro 470W",
                "parametros_clave": {"potencia_w": 470},
            },
        ],
    }


@pytest.fixture
def sample_extracted_battery() -> dict[str, Any]:
    """Sample LLM-extracted metadata for a battery with subcategoria."""
    return {
        "nombre_comercial": "Sunset Gel",
        "fabricante": "Sunset",
        "descripcion": "Batería solar de ciclo profundo tipo Gel.",
        "parametros_comunes": {
            "tipo": "Gel",
        },
        "variantes": [
            {
                "modelo": "Gel 100Ah",
                "parametros_clave": {"capacidad": 100},
            },
            {
                "modelo": "Gel 250Ah",
                "parametros_clave": {"capacidad": 250},
            },
        ],
    }


@pytest.fixture
def pdf_info_panel() -> dict[str, Any]:
    """PDF discovery info for a panel (no subcategoria)."""
    return {
        "s3_key": "raw/paneles/Jinko Tiger Pro.pdf",
        "filename": "Jinko Tiger Pro",
        "categoria": "paneles",
        "subcategoria": None,
        "nombre_comercial": "Jinko Tiger Pro",
    }


@pytest.fixture
def pdf_info_battery() -> dict[str, Any]:
    """PDF discovery info for a battery (with subcategoria)."""
    return {
        "s3_key": "raw/baterias/gel/Sunset Gel.pdf",
        "filename": "Sunset Gel",
        "categoria": "baterias",
        "subcategoria": "gel",
        "nombre_comercial": "Sunset Gel",
    }


@pytest.fixture
def existing_index() -> dict[str, Any]:
    """Sample existing catalog index with one product."""
    return {
        "version": "1.1.0",
        "generado_en": "2026-03-24T10:00:00+00:00",
        "generado_por": "ai-pipeline",
        "productos": [
            {
                "id": "jinko-tiger-pro",
                "nombre_comercial": "Jinko Tiger Pro",
                "categoria": "paneles",
                "fabricante": "Jinko",
                "ruta_s3": "raw/paneles/Jinko Tiger Pro.pdf",
                "variantes": [
                    {
                        "modelo": "Tiger Pro 460W",
                        "parametros_clave": {"potencia_w": 460},
                    }
                ],
            }
        ],
    }


@pytest.fixture
def temp_source_dir() -> str:
    """Create a temporary directory with a mock S3-like structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # paneles/ (one level)
        os.makedirs(os.path.join(tmpdir, "paneles"))
        Path(os.path.join(tmpdir, "paneles", "Jinko Tiger Pro.pdf")).write_bytes(
            b"%PDF-1.4 mock"
        )

        # baterias/gel/ (two levels)
        os.makedirs(os.path.join(tmpdir, "baterias", "gel"))
        Path(os.path.join(tmpdir, "baterias", "gel", "Sunset Gel.pdf")).write_bytes(
            b"%PDF-1.4 mock"
        )

        # baterias/litio/ (two levels)
        os.makedirs(os.path.join(tmpdir, "baterias", "litio"))
        Path(
            os.path.join(tmpdir, "baterias", "litio", "Huawei LUNA2000.pdf")
        ).write_bytes(b"%PDF-1.4 mock")

        # inversores/multifuncionales/ (two levels)
        os.makedirs(os.path.join(tmpdir, "inversores", "multifuncionales"))
        Path(
            os.path.join(tmpdir, "inversores", "multifuncionales", "Voltronic.pdf")
        ).write_bytes(b"%PDF-1.4 mock")

        yield tmpdir


@pytest.fixture
def schema_path() -> str:
    """Path to the catalog_index JSON schema."""
    # Navigate relative to this test file
    base = Path(__file__).parent.parent.parent
    schema = base / "docs" / "schemas" / "catalog_index.schema.json"
    if schema.exists():
        return str(schema)
    pytest.skip("Schema file not found")


# ---------------------------------------------------------------------------
# Unit tests: typed extraction identity and reconciliation
# ---------------------------------------------------------------------------


def _extracted_product(name: str = "Jinko Tiger Pro") -> ExtractedProduct:
    return ExtractedProduct(
        nombre_comercial=name,
        fabricante="Jinko",
        descripcion=None,
        url_fabricante=None,
        version_ficha=None,
        categoria="paneles",
        subcategoria=None,
        ruta_s3=f"raw/paneles/{name}.pdf",
        parametros_comunes=[
            {"name": "tipo_celda", "value": "monocristalino"}
        ],
        variantes=[
            {
                "modelo": "Tiger Pro 460W",
                "parametros_clave": [{"name": "potencia_w", "value": 460}],
            }
        ],
    )


def _document_extraction(
    document_id: str,
    product_name: str = "Jinko Tiger Pro",
) -> DocumentExtraction:
    return DocumentExtraction(
        document_id=document_id,
        status=ExtractionStatus.NORMAL,
        products=[_extracted_product(product_name)],
        review_reasons=[],
    )


def _trusted_document(name: str) -> TrustedDocument:
    s3_key = f"raw/paneles/{name}.pdf"
    return TrustedDocument(
        s3_key=s3_key,
        pdf_info={
            "s3_key": s3_key,
            "filename": name,
            "categoria": "paneles",
            "subcategoria": None,
            "nombre_comercial": name,
        },
        file_id=f"file-{name.lower().replace(' ', '-')}",
    )


def _assert_schema_objects_closed(node: Any, path: str = "$") -> None:
    """Assert recursively that every JSON Schema object forbids extra fields."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False, path
        for key, value in node.items():
            _assert_schema_objects_closed(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _assert_schema_objects_closed(value, f"{path}[{index}]")


class TestExtractionDtos:
    def test_generated_schema_closes_every_object_node(self) -> None:
        _assert_schema_objects_closed(ExtractionBatch.model_json_schema())

    def test_batch_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            ExtractionBatch.model_validate({"documents": [], "unexpected": True})

    def test_document_rejects_unknown_fields(self) -> None:
        payload = _document_extraction("doc-a").model_dump()
        payload["unexpected"] = True

        with pytest.raises(ValidationError):
            DocumentExtraction.model_validate(payload)

    def test_nested_product_rejects_unknown_fields(self) -> None:
        payload = _extracted_product().model_dump()
        payload["invented"] = "not allowed"

        with pytest.raises(ValidationError):
            ExtractedProduct.model_validate(payload)

    def test_variant_rejects_unknown_fields(self) -> None:
        payload = _extracted_product().variantes[0].model_dump()
        payload["unexpected"] = True

        with pytest.raises(ValidationError):
            type(_extracted_product().variantes[0]).model_validate(payload)

    def test_accepts_typed_technical_parameter_pairs(self) -> None:
        payload = _extracted_product().model_dump()
        payload["parametros_comunes"] = [
            {"name": "tipo_celda", "value": "monocristalino"}
        ]
        payload["variantes"][0]["parametros_clave"] = [
            {"name": "potencia_w", "value": 460}
        ]

        product = ExtractedProduct.model_validate(payload)

        assert product.parametros_comunes[0].name == "tipo_celda"
        assert product.parametros_comunes[0].value == "monocristalino"
        assert product.variantes[0].parametros_clave[0].name == "potencia_w"
        assert product.variantes[0].parametros_clave[0].value == 460

    @pytest.mark.parametrize(
        ("field", "expected_location"),
        [
            ("parametros_comunes", ("parametros_comunes", 0, "unexpected")),
            (
                "parametros_clave",
                ("variantes", 0, "parametros_clave", 0, "unexpected"),
            ),
        ],
    )
    def test_technical_parameter_rejects_unknown_fields(
        self,
        field: str,
        expected_location: tuple[str | int, ...],
    ) -> None:
        payload = _extracted_product().model_dump()
        parameter = {"name": "rating", "value": 460, "unexpected": True}
        if field == "parametros_comunes":
            payload[field] = [parameter]
        else:
            payload["variantes"][0][field] = [parameter]

        with pytest.raises(ValidationError) as error:
            ExtractedProduct.model_validate(payload)

        assert error.value.errors()[0]["loc"] == expected_location


class TestTrustedMap:
    def test_duplicate_expected_ids_fail_closed(self) -> None:
        documents = [_trusted_document("Series A"), _trusted_document("Series B")]

        with pytest.raises(ExtractionProtocolError, match="duplicate expected"):
            build_trusted_map(documents, document_id_factory=lambda: "same-id")


class TestReconcileBatch:
    def test_exact_identity_set_reconciles(self) -> None:
        trusted_map = {"doc-a": _trusted_document("Jinko Tiger Pro")}
        parsed = ExtractionBatch(documents=[_document_extraction("doc-a")])

        reconciled = reconcile_batch(parsed, trusted_map)

        assert reconciled == [
            (parsed.documents[0].products[0], trusted_map["doc-a"])
        ]

    def test_complete_out_of_order_batch_reconciles_by_identity(self) -> None:
        trusted_map = {
            "doc-a": _trusted_document("Series A"),
            "doc-b": _trusted_document("Series B"),
        }
        parsed = ExtractionBatch(
            documents=[
                _document_extraction("doc-b", "Series B"),
                _document_extraction("doc-a", "Series A"),
            ]
        )

        reconciled = reconcile_batch(parsed, trusted_map)

        assert [trusted.s3_key for _, trusted in reconciled] == [
            "raw/paneles/Series B.pdf",
            "raw/paneles/Series A.pdf",
        ]

    @pytest.mark.parametrize(
        ("expected_ids", "returned_ids", "message"),
        [
            (("doc-a", "doc-b"), ("doc-a",), "missing"),
            (("doc-a",), ("doc-a", "doc-extra"), "extra"),
            (("doc-a", "doc-b"), ("doc-a", "doc-unknown"), "unknown"),
        ],
    )
    def test_identity_set_anomalies_fail_closed(
        self,
        expected_ids: tuple[str, ...],
        returned_ids: tuple[str, ...],
        message: str,
    ) -> None:
        trusted_map = {
            document_id: _trusted_document(f"Series {index}")
            for index, document_id in enumerate(expected_ids)
        }
        parsed = ExtractionBatch(
            documents=[_document_extraction(document_id) for document_id in returned_ids]
        )

        with pytest.raises(ExtractionProtocolError, match=message):
            reconcile_batch(parsed, trusted_map)

    def test_duplicate_returned_id_fails_closed(self) -> None:
        trusted_map = {"doc-a": _trusted_document("Series A")}
        parsed = ExtractionBatch(
            documents=[
                _document_extraction("doc-a"),
                _document_extraction("doc-a"),
            ]
        )

        with pytest.raises(ExtractionProtocolError, match="duplicate returned"):
            reconcile_batch(parsed, trusted_map)


class TestExtractionClassification:
    def test_one_series_with_multiple_variants_is_normal(self) -> None:
        product = ExtractedProduct.model_validate(
            {
                **_extracted_product().model_dump(),
                "variantes": [
                    {
                        "modelo": "Tiger Pro 460W",
                        "parametros_clave": [
                            {"name": "potencia_w", "value": 460}
                        ],
                    },
                    {
                        "modelo": "Tiger Pro 470W",
                        "parametros_clave": [
                            {"name": "potencia_w", "value": 470}
                        ],
                    },
                ],
            }
        )
        document = _document_extraction("doc-a").model_copy(
            update={"products": [product]}
        )
        trusted = _trusted_document("Jinko Tiger Pro")

        reconciled = reconcile_batch(
            ExtractionBatch(documents=[document]), {"doc-a": trusted}
        )

        assert [variant.modelo for variant in reconciled[0][0].variantes] == [
            "Tiger Pro 460W",
            "Tiger Pro 470W",
        ]

    def test_zero_products_needs_review(self) -> None:
        document = _document_extraction("doc-a").model_copy(update={"products": []})

        with pytest.raises(ExtractionNeedsReview, match="zero products"):
            reconcile_batch(
                ExtractionBatch(documents=[document]),
                {"doc-a": _trusted_document("Jinko Tiger Pro")},
            )

    def test_product_with_zero_variants_needs_review(self) -> None:
        product = _extracted_product().model_copy(update={"variantes": []})
        document = _document_extraction("doc-a").model_copy(
            update={"products": [product]}
        )

        with pytest.raises(ExtractionNeedsReview, match="zero variants"):
            reconcile_batch(
                ExtractionBatch(documents=[document]),
                {"doc-a": _trusted_document("Jinko Tiger Pro")},
            )

    def test_multiple_unrelated_products_need_review(self) -> None:
        document = _document_extraction("doc-a").model_copy(
            update={
                "products": [
                    _extracted_product("Jinko Tiger Pro"),
                    _extracted_product("Unrelated Series"),
                ]
            }
        )

        with pytest.raises(ExtractionNeedsReview, match="multiple products"):
            reconcile_batch(
                ExtractionBatch(documents=[document]),
                {"doc-a": _trusted_document("Jinko Tiger Pro")},
            )

    def test_suspicious_routing_mismatch_needs_review(self) -> None:
        product = _extracted_product().model_copy(
            update={
                "categoria": "baterias",
                "subcategoria": "litio",
                "ruta_s3": "raw/baterias/litio/Other.pdf",
            }
        )
        document = _document_extraction("doc-a").model_copy(
            update={"products": [product]}
        )

        with pytest.raises(ExtractionNeedsReview, match="routing mismatch"):
            reconcile_batch(
                ExtractionBatch(documents=[document]),
                {"doc-a": _trusted_document("Jinko Tiger Pro")},
            )


class TestTrustedProductConversion:
    def test_trusted_routing_fields_override_model_claims(self) -> None:
        extracted = _extracted_product().model_copy(
            update={
                "categoria": "baterias",
                "subcategoria": "litio",
                "ruta_s3": "raw/baterias/litio/Other.pdf",
            }
        )
        trusted = _trusted_document("Jinko Tiger Pro")

        entry = build_product_entry(extracted, trusted)

        assert entry["ruta_s3"] == "raw/paneles/Jinko Tiger Pro.pdf"
        assert entry["categoria"] == "paneles"
        assert "subcategoria" not in entry
        assert entry["parametros_comunes"] == {
            "tipo_celda": "monocristalino"
        }
        assert entry["variantes"][0]["parametros_clave"] == {"potencia_w": 460}


# ---------------------------------------------------------------------------
# Unit tests: _parse_s3_key
# ---------------------------------------------------------------------------


class TestParseS3Key:
    def test_one_level(self) -> None:
        result = _parse_s3_key("raw/paneles/Jinko Tiger Pro.pdf", "raw/")
        assert result is not None
        assert result["categoria"] == "paneles"
        assert result["subcategoria"] is None
        assert result["nombre_comercial"] == "Jinko Tiger Pro"

    def test_two_levels(self) -> None:
        result = _parse_s3_key("raw/baterias/gel/Sunset Gel.pdf", "raw/")
        assert result is not None
        assert result["categoria"] == "baterias"
        assert result["subcategoria"] == "gel"
        assert result["nombre_comercial"] == "Sunset Gel"

    def test_invalid_path(self) -> None:
        result = _parse_s3_key("raw/orphan.pdf", "raw/")
        assert result is None

    def test_custom_prefix(self) -> None:
        result = _parse_s3_key("data/paneles/Panel X.pdf", "data/")
        assert result is not None
        assert result["categoria"] == "paneles"


# ---------------------------------------------------------------------------
# Unit tests: _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self) -> None:
        assert _slugify("Jinko Tiger Pro") == "jinko-tiger-pro"

    def test_special_chars(self) -> None:
        assert _slugify("Growatt SP-5000TL") == "growatt-sp-5000tl"

    def test_uppercase(self) -> None:
        assert _slugify("HUAWEI LUNA2000") == "huawei-luna2000"

    def test_spaces_and_hyphens(self) -> None:
        assert _slugify("Victron  SmartSolar  MPPT") == "victron-smartsolar-mppt"


# ---------------------------------------------------------------------------
# Unit tests: filter_new_pdfs
# ---------------------------------------------------------------------------


class TestFilterNewPdfs:
    def test_filters_existing(self, existing_index: dict) -> None:
        pdfs = [
            {
                "s3_key": "raw/paneles/Jinko Tiger Pro.pdf",
                "categoria": "paneles",
                "subcategoria": None,
                "nombre_comercial": "Jinko Tiger Pro",
            },
            {
                "s3_key": "raw/paneles/Trina Vertex.pdf",
                "categoria": "paneles",
                "subcategoria": None,
                "nombre_comercial": "Trina Vertex",
            },
        ]
        result = filter_new_pdfs(pdfs, existing_index)
        assert len(result) == 1
        assert result[0]["nombre_comercial"] == "Trina Vertex"

    def test_no_existing_index(self) -> None:
        pdfs = [
            {
                "s3_key": "raw/paneles/Panel.pdf",
                "categoria": "paneles",
                "subcategoria": None,
                "nombre_comercial": "Panel",
            }
        ]
        result = filter_new_pdfs(pdfs, None)
        assert len(result) == 1

    def test_all_already_indexed(self, existing_index: dict) -> None:
        pdfs = [
            {
                "s3_key": "raw/paneles/Jinko Tiger Pro.pdf",
                "categoria": "paneles",
                "subcategoria": None,
                "nombre_comercial": "Jinko Tiger Pro",
            }
        ]
        result = filter_new_pdfs(pdfs, existing_index)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Unit tests: build_product_entry
# ---------------------------------------------------------------------------


class TestBuildProductEntry:
    def test_panel_entry(
        self, sample_extracted_panel: dict, pdf_info_panel: dict
    ) -> None:
        entry = build_product_entry(sample_extracted_panel, pdf_info_panel)
        assert entry["id"] == "jinko-tiger-pro"
        assert entry["nombre_comercial"] == "Jinko Tiger Pro"
        assert entry["categoria"] == "paneles"
        assert entry["fabricante"] == "Jinko"
        assert entry["ruta_s3"] == "raw/paneles/Jinko Tiger Pro.pdf"
        assert "subcategoria" not in entry
        assert len(entry["variantes"]) == 2
        assert entry["parametros_comunes"]["tipo_celda"] == "monocristalino"

    def test_battery_with_subcategoria(
        self, sample_extracted_battery: dict, pdf_info_battery: dict
    ) -> None:
        entry = build_product_entry(sample_extracted_battery, pdf_info_battery)
        assert entry["id"] == "sunset-gel"
        assert entry["categoria"] == "baterias"
        assert entry["subcategoria"] == "gel"
        assert entry["ruta_s3"] == "raw/baterias/gel/Sunset Gel.pdf"
        assert entry["parametros_comunes"]["tipo"] == "Gel"
        assert len(entry["variantes"]) == 2

    def test_missing_fields_use_defaults(self, pdf_info_panel: dict) -> None:
        """When extracted metadata is minimal, defaults are used."""
        entry = build_product_entry({}, pdf_info_panel)
        assert entry["nombre_comercial"] == "Jinko Tiger Pro"
        assert entry["fabricante"] == "Desconocido"
        assert entry["variantes"] == []


# ---------------------------------------------------------------------------
# Unit tests: build_catalog_index
# ---------------------------------------------------------------------------


class TestBuildCatalogIndex:
    def test_new_index(
        self, sample_extracted_panel: dict, pdf_info_panel: dict
    ) -> None:
        products = [build_product_entry(sample_extracted_panel, pdf_info_panel)]
        catalog = build_catalog_index(products)

        assert "version" in catalog
        assert "generado_en" in catalog
        assert catalog["generado_por"] == "ai-pipeline"
        assert len(catalog["productos"]) == 1

    def test_merge_with_existing(
        self,
        sample_extracted_battery: dict,
        pdf_info_battery: dict,
        existing_index: dict,
    ) -> None:
        new_products = [build_product_entry(sample_extracted_battery, pdf_info_battery)]
        catalog = build_catalog_index(new_products, existing_index)
        assert len(catalog["productos"]) == 2

    def test_sorting(self, sample_extracted_panel: dict, pdf_info_panel: dict) -> None:
        """Products are sorted by categoria then nombre_comercial."""
        battery_entry = {
            "id": "sunset-gel",
            "nombre_comercial": "Sunset Gel",
            "categoria": "baterias",
            "fabricante": "Sunset",
            "ruta_s3": "raw/baterias/gel/Sunset Gel.pdf",
            "variantes": [],
        }
        products = [
            battery_entry,
            build_product_entry(sample_extracted_panel, pdf_info_panel),
        ]
        catalog = build_catalog_index(products)
        assert catalog["productos"][0]["categoria"] == "baterias"
        assert catalog["productos"][1]["categoria"] == "paneles"


# ---------------------------------------------------------------------------
# Unit tests: list_local_pdfs
# ---------------------------------------------------------------------------


class TestListLocalPdfs:
    def test_discovers_flat_structure(self, temp_source_dir: str) -> None:
        pdfs = list_local_pdfs(temp_source_dir)
        # Should find all 4 PDFs
        assert len(pdfs) == 4

    def test_parses_categoria(self, temp_source_dir: str) -> None:
        pdfs = list_local_pdfs(temp_source_dir)
        categorias = {p["categoria"] for p in pdfs}
        assert categorias == {"paneles", "baterias", "inversores"}

    def test_parses_subcategoria(self, temp_source_dir: str) -> None:
        pdfs = list_local_pdfs(temp_source_dir)
        subcategorias = {p["subcategoria"] for p in pdfs if p.get("subcategoria")}
        assert subcategorias == {"gel", "litio", "multifuncionales"}

    def test_panel_no_subcategoria(self, temp_source_dir: str) -> None:
        pdfs = list_local_pdfs(temp_source_dir)
        panel = next(p for p in pdfs if p["categoria"] == "paneles")
        assert panel["subcategoria"] is None

    def test_nonexistent_dir(self) -> None:
        pdfs = list_local_pdfs("/nonexistent/path")
        assert pdfs == []


# ---------------------------------------------------------------------------
# Unit tests: save_local
# ---------------------------------------------------------------------------


class TestSaveLocal:
    def test_creates_file(self, tmp_path: Path) -> None:
        output = str(tmp_path / "subdir" / "catalog_index.json")
        catalog = {
            "version": "1.1.0",
            "generado_en": "2026-03-24T00:00:00Z",
            "productos": [],
        }
        save_local(catalog, output)
        assert os.path.exists(output)

    def test_valid_json(self, tmp_path: Path) -> None:
        output = str(tmp_path / "catalog_index.json")
        catalog = {
            "version": "1.1.0",
            "generado_en": "2026-03-24T00:00:00Z",
            "productos": [{"id": "test"}],
        }
        save_local(catalog, output)
        with open(output) as f:
            loaded = json.load(f)
        assert loaded["productos"][0]["id"] == "test"


# ---------------------------------------------------------------------------
# Unit tests: validate_index
# ---------------------------------------------------------------------------


class TestValidateIndex:
    def test_valid_catalog(self, schema_path: str) -> None:
        catalog = {
            "version": "1.0.0",
            "generado_en": "2026-03-24T14:30:00-05:00",
            "productos": [
                {
                    "id": "jinko-tiger-pro",
                    "nombre_comercial": "Jinko Tiger Pro",
                    "categoria": "paneles",
                    "fabricante": "Jinko",
                    "ruta_s3": "raw/paneles/Jinko Tiger Pro.pdf",
                    "parametros_comunes": {"tipo_celda": "monocristalino"},
                    "variantes": [
                        {
                            "modelo": "Tiger Pro 460W",
                            "parametros_clave": {"potencia_w": 460},
                        }
                    ],
                }
            ],
        }
        errors = validate_index(catalog, schema_path)
        assert errors == [], f"Unexpected validation errors: {errors}"

    def test_invalid_catalog(self, schema_path: str) -> None:
        catalog = {
            "version": "1.0.0",
            "generado_en": "2026-03-24T14:30:00-05:00",
            "productos": [
                {
                    # Missing required fields: id, nombre_comercial, etc.
                    "categoria": "paneles",
                }
            ],
        }
        errors = validate_index(catalog, schema_path)
        assert len(errors) > 0

    def test_missing_schema(self) -> None:
        catalog = {"version": "1.0.0", "generado_en": "", "productos": []}
        errors = validate_index(catalog, "/nonexistent/schema.json")
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Integration test: full pipeline with local source (mocked AI)
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    @patch("generate_index.extract_metadata_batch")
    def test_full_pipeline_local(
        self,
        mock_extract: MagicMock,
        temp_source_dir: str,
        schema_path: str,
        tmp_path: Path,
    ) -> None:
        """Test the full pipeline with mocked AI extraction."""
        # Mock returns items in the SAME ORDER as the PDFs are discovered.
        # Local PDFs are sorted alphabetically by s3_key:
        #   1. baterias/gel/Sunset Gel.pdf
        #   2. baterias/litio/Huawei LUNA2000.pdf
        #   3. inversores/multifuncionales/Voltronic.pdf
        #   4. paneles/Jinko Tiger Pro.pdf
        # With batch_size=2, batch 1 = [1,2], batch 2 = [3,4].
        mock_extract.side_effect = [
            # Batch 1: baterias/gel + baterias/litio
            [
                {
                    "nombre_comercial": "Sunset Gel",
                    "fabricante": "Sunset",
                    "parametros_comunes": {"tipo": "Gel"},
                    "variantes": [
                        {
                            "modelo": "Gel 100Ah",
                            "parametros_clave": {"capacidad": 100},
                        }
                    ],
                },
                {
                    "nombre_comercial": "Huawei LUNA2000",
                    "fabricante": "Huawei",
                    "parametros_comunes": {"tipo": "Litio", "nivel_tension": 48},
                    "variantes": [
                        {
                            "modelo": "LUNA2000-5 kWh",
                            "parametros_clave": {"capacidad": 5},
                        }
                    ],
                },
            ],
            # Batch 2: inversores/multifuncionales + paneles
            [
                {
                    "nombre_comercial": "Voltronic Axpert",
                    "fabricante": "Voltronic",
                    "parametros_comunes": {
                        "tipo": "multifuncional",
                        "nivel_tension": 48,
                    },
                    "variantes": [
                        {
                            "modelo": "Axpert 5kVA",
                            "parametros_clave": {"capacidad": 5000},
                        }
                    ],
                },
                {
                    "nombre_comercial": "Jinko Tiger Pro",
                    "fabricante": "Jinko",
                    "parametros_comunes": {"tipo_celda": "monocristalino"},
                    "variantes": [
                        {
                            "modelo": "Tiger Pro 460W",
                            "parametros_clave": {"potencia_w": 460},
                        }
                    ],
                },
            ],
        ]

        output_path = str(tmp_path / "catalog_index.json")

        from generate_index import run_pipeline

        exit_code = run_pipeline(
            s3_manager=None,
            source_dir=temp_source_dir,
            prefix="raw/",
            output_path=output_path,
            index_s3_key="index/catalog_index.json",
            schema_path=schema_path,
            batch_size=2,
            local_only=True,
            dry_run=False,
            force=True,
            api_key="test-key",
            model="gpt-4o",
        )

        assert exit_code == 0
        assert os.path.exists(output_path)

        with open(output_path) as f:
            catalog = json.load(f)

        assert catalog["version"] == "1.1.0"
        assert catalog["generado_por"] == "ai-pipeline"
        assert len(catalog["productos"]) == 4

        # Verify subcategoria was preserved
        batteries = [p for p in catalog["productos"] if p["categoria"] == "baterias"]
        assert len(batteries) == 2
        gel_battery = next(b for b in batteries if b.get("subcategoria") == "gel")
        assert gel_battery["nombre_comercial"] == "Sunset Gel"

    def test_dry_run(self, temp_source_dir: str, tmp_path: Path) -> None:
        """Dry run should not create output file."""
        output_path = str(tmp_path / "catalog_index.json")

        from generate_index import run_pipeline

        exit_code = run_pipeline(
            s3_manager=None,
            source_dir=temp_source_dir,
            prefix="raw/",
            output_path=output_path,
            index_s3_key="index/catalog_index.json",
            schema_path="/nonexistent/schema.json",
            batch_size=5,
            local_only=True,
            dry_run=True,
            force=True,
            api_key="test-key",
            model="gpt-4o",
        )

        assert exit_code == 0
        assert not os.path.exists(output_path)

    def test_idempotency(
        self,
        existing_index: dict,
        tmp_path: Path,
        schema_path: str,
    ) -> None:
        """Running twice without new PDFs should not change the index."""
        # Save existing index locally
        existing_path = str(tmp_path / "catalog_index.json")
        save_local(existing_index, existing_path)

        # Create a source dir with the same PDF
        source_dir = str(tmp_path / "source")
        os.makedirs(os.path.join(source_dir, "paneles"))
        Path(os.path.join(source_dir, "paneles", "Jinko Tiger Pro.pdf")).write_bytes(
            b"%PDF-1.4 mock"
        )

        from generate_index import run_pipeline

        exit_code = run_pipeline(
            s3_manager=None,
            source_dir=source_dir,
            prefix="raw/",
            output_path=existing_path,
            index_s3_key="index/catalog_index.json",
            schema_path=schema_path,
            batch_size=5,
            local_only=True,
            dry_run=False,
            force=False,  # Idempotency enabled
            api_key="test-key",
            model="gpt-4o",
        )

        assert exit_code == 0

        with open(existing_path) as f:
            catalog = json.load(f)

        # Should still have only 1 product (the existing one)
        assert len(catalog["productos"]) == 1
        assert catalog["productos"][0]["nombre_comercial"] == "Jinko Tiger Pro"
