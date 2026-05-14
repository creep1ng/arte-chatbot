"""
Unit tests for the tools.py module.

Tests the tool definitions for OpenAI function calling, specifically
the `leer_ficha_tecnica` function for reading technical datasheets.
"""

import pytest
from backend.app import tools


class TestToolDefinitions:
    """Tests for get_tool_definitions() function."""

    def test_get_tool_definitions_returns_list(self) -> None:
        """Test that get_tool_definitions returns a list."""
        result = tools.get_tool_definitions()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_tool_definitions_contains_required_fields(self) -> None:
        """Test that tool schema contains required fields."""
        result = tools.get_tool_definitions()
        assert len(result) >= 1

        # Find the leer_ficha_tecnica tool
        tool = None
        for t in result:
            if t.get("name") == "leer_ficha_tecnica":
                tool = t
                break

        assert tool is not None, "leer_ficha_tecnica tool not found"

        # Check top-level structure (Responses API format)
        assert tool.get("type") == "function"
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool

    def test_tool_has_correct_name(self) -> None:
        """Test that tool has correct name."""
        result = tools.get_tool_definitions()
        tool = result[0]
        assert tool["name"] == "leer_ficha_tecnica"

    def test_tool_has_description(self) -> None:
        """Test that tool has a description."""
        result = tools.get_tool_definitions()
        tool = result[0]
        description = tool["description"]
        assert len(description) > 0
        assert "ficha técnica" in description.lower()


class TestToolParameters:
    """Tests for tool parameter schema."""

    def test_parameters_contain_required_fields(self) -> None:
        """Test parameters contain ruta_s3, categoria, fabricante, modelo."""
        result = tools.get_tool_definitions()
        tool = result[0]
        params = tool["parameters"]
        properties = params.get("properties", {})

        required_props = ["ruta_s3", "categoria", "fabricante", "modelo"]
        for prop in required_props:
            assert prop in properties, f"Missing required property: {prop}"

    def test_ruta_s3_parameter(self) -> None:
        """Test ruta_s3 parameter schema."""
        result = tools.get_tool_definitions()
        tool = result[0]
        params = tool["parameters"]
        properties = params.get("properties", {})

        ruta_s3 = properties["ruta_s3"]
        assert ruta_s3["type"] == "string"
        assert "description" in ruta_s3
        assert "S3" in ruta_s3["description"] or "s3" in ruta_s3["description"].lower()

    def test_categoria_parameter_has_enum(self) -> None:
        """Test categoria parameter has valid enum options."""
        result = tools.get_tool_definitions()
        tool = result[0]
        params = tool["parameters"]
        properties = params.get("properties", {})

        categoria = properties["categoria"]
        assert "enum" in categoria

        expected_categories = [
            "paneles",
            "inversores",
            "controladores",
            "baterias",
            "microinversores",
            "protecciones",
        ]
        assert categoria["enum"] == expected_categories

    def test_fabricante_parameter(self) -> None:
        """Test fabricante parameter schema."""
        result = tools.get_tool_definitions()
        tool = result[0]
        params = tool["parameters"]
        properties = params.get("properties", {})

        fabricante = properties["fabricante"]
        assert fabricante["type"] == "string"
        assert "description" in fabricante
        assert (
            "fabricante" in fabricante["description"].lower()
            or "marca" in fabricante["description"].lower()
        )

    def test_modelo_parameter(self) -> None:
        """Test modelo parameter schema."""
        result = tools.get_tool_definitions()
        tool = result[0]
        params = tool["parameters"]
        properties = params.get("properties", {})

        modelo = properties["modelo"]
        assert modelo["type"] == "string"
        assert "description" in modelo


class TestToolRequiredFields:
    """Tests for required parameters."""

    def test_parameters_required_list(self) -> None:
        """Test that only categoria is required."""
        result = tools.get_tool_definitions()
        tool = result[0]
        params = tool["parameters"]

        required = params.get("required", [])
        assert "categoria" in required
        # Other fields are optional for flexible search
        assert "ruta_s3" not in required
        assert "fabricante" not in required
        assert "modelo" not in required

    def test_strict_is_false(self) -> None:
        """Test that strict mode is disabled for flexible tool calling."""
        result = tools.get_tool_definitions()
        tool = result[0]
        assert tool.get("strict") is False


class TestConstants:
    """Tests for module constants."""

    def test_datasheet_categories_constant(self) -> None:
        """Test DATASHEET_CATEGORIES constant exists and is correct."""
        assert hasattr(tools, "DATASHEET_CATEGORIES")
        assert tools.DATASHEET_CATEGORIES == [
            "paneles",
            "inversores",
            "controladores",
            "baterias",
            "microinversores",
            "protecciones",
        ]

    def test_available_tools_constant(self) -> None:
        """Test AVAILABLE_TOOLS constant exists and contains tools."""
        assert hasattr(tools, "AVAILABLE_TOOLS")
        assert isinstance(tools.AVAILABLE_TOOLS, list)
        assert len(tools.AVAILABLE_TOOLS) > 0

    def test_leer_ficha_tecnica_tool_constant(self) -> None:
        """Test LEER_FICHA_TECNICA_TOOL constant exists."""
        assert hasattr(tools, "LEER_FICHA_TECNICA_TOOL")
        assert tools.LEER_FICHA_TECNICA_TOOL["name"] == "leer_ficha_tecnica"


class TestPathTraversalValidation:
    """Tests for S3 path validation against path traversal attacks."""

    def test_validate_s3_path_accepts_valid_paths(self) -> None:
        """Test that valid paths are accepted."""
        from backend.app.tools import validate_s3_path

        valid_paths = [
            "paneles/jinko-tiger-pro-460w.pdf",
            "inversores/fronius-primo-5kw.pdf",
            "controladores/epever-20a.pdf",
            "baterias/BYD-battery-box.pdf",
        ]
        for path in valid_paths:
            validate_s3_path(path)

    def test_validate_s3_path_rejects_parent_traversal(self) -> None:
        """Test that ../ path traversal is rejected."""
        from backend.app.tools import PathTraversalError, validate_s3_path

        malicious_paths = [
            "../index/catalog_index.json",
            "paneles/../../../etc/passwd",
            "paneles/../../secret.pdf",
        ]
        for path in malicious_paths:
            with pytest.raises(PathTraversalError):
                validate_s3_path(path)

    def test_validate_s3_path_rejects_absolute_paths(self) -> None:
        """Test that absolute paths starting with / are rejected."""
        from backend.app.tools import PathTraversalError, validate_s3_path

        absolute_paths = [
            "/etc/passwd",
            "/paneles/jinko.pdf",
            "/tmp/../../../etc/passwd",
        ]
        for path in absolute_paths:
            with pytest.raises(PathTraversalError):
                validate_s3_path(path)

    def test_validate_s3_path_rejects_invalid_category(self) -> None:
        """Test that paths not starting with valid category are rejected."""
        from backend.app.tools import PathTraversalError, validate_s3_path

        invalid_category_paths = [
            "secret/file.pdf",
            "config/data.json",
            "raw/paneles/jinko.pdf",
        ]
        for path in invalid_category_paths:
            with pytest.raises(PathTraversalError):
                validate_s3_path(path)

    def test_validate_s3_path_rejects_empty_path(self) -> None:
        """Test that empty paths raise PathTraversalError."""
        from backend.app.tools import PathTraversalError, validate_s3_path

        with pytest.raises(PathTraversalError):
            validate_s3_path("")

    def test_validate_s3_path_error_message_is_informative(self) -> None:
        """Test that error messages provide useful information."""
        from backend.app.tools import PathTraversalError, validate_s3_path

        with pytest.raises(PathTraversalError) as exc_info:
            validate_s3_path("../index/catalog_index.json")
        assert "Path traversal" in str(exc_info.value)

        with pytest.raises(PathTraversalError) as exc_info:
            validate_s3_path("raw/paneles/jinko.pdf")
        assert "Invalid category prefix" in str(exc_info.value)
