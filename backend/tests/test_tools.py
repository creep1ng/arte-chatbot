"""
Unit tests for the tools.py module.

Tests the tool definitions for OpenAI function calling, specifically
the `leer_ficha_tecnica` function for reading technical datasheets.
"""

from typing import Any

import pytest
from backend.app import tools


def _get_buscar_producto_tool() -> dict[str, Any]:
    """Return the buscar_producto tool definition."""
    result = tools.get_tool_definitions()
    for tool in result:
        function = tool.get("function")
        if function and function.get("name") == "buscar_producto":
            return tool
    raise AssertionError("buscar_producto tool not found in tool definitions")


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
            function_block = t.get("function", {})
            if function_block.get("name") == "leer_ficha_tecnica":
                tool = t
                break

        assert tool is not None, "leer_ficha_tecnica tool not found"

        # Check top-level structure (Responses API format)
        function_block = tool.get("function", {})
        assert tool.get("type") == "function"
        assert "name" in function_block
        assert "description" in function_block
        assert "parameters" in function_block

    def test_tool_has_correct_name(self) -> None:
        """Test that tool has correct name."""
        result = tools.get_tool_definitions()
        tool = result[0]
        assert tool["function"]["name"] == "leer_ficha_tecnica"

    def test_tool_has_description(self) -> None:
        """Test that tool has a description."""
        result = tools.get_tool_definitions()
        tool = result[0]
        function = tool["function"]
        description = function["description"]
        assert len(description) > 0
        assert "ficha técnica" in description.lower()


class TestBuscarProductoTool:
    """Tests for buscar_producto tool definition."""

    def test_buscar_producto_tool_exists(self) -> None:
        """Ensure buscar_producto tool exists in definitions."""
        tool = _get_buscar_producto_tool()
        assert tool.get("function", {}).get("name") == "buscar_producto"

    def test_buscar_producto_schema_has_correct_name(self) -> None:
        """Validate schema uses function type with correct name."""
        tool = _get_buscar_producto_tool()
        assert tool.get("type") == "function"
        function_block = tool.get("function", {})
        assert function_block.get("name") == "buscar_producto"

    def test_buscar_producto_categoria_is_required(self) -> None:
        """Ensure categoria field is required."""
        tool = _get_buscar_producto_tool()
        required = tool["function"]["parameters"].get("required", [])
        assert "categoria" in required

    def test_buscar_producto_categoria_has_correct_enum(self) -> None:
        """Validate categoria enum matches expected categories."""
        tool = _get_buscar_producto_tool()
        categoria = tool["function"]["parameters"]["properties"]["categoria"]
        expected = ["paneles", "inversores", "controladores", "baterias"]
        assert categoria.get("enum") == expected

    def test_buscar_producto_other_fields_are_optional(self) -> None:
        """Ensure other filter fields exist and remain optional."""
        tool = _get_buscar_producto_tool()
        params = tool["function"]["parameters"]
        properties = params.get("properties", {})
        required = params.get("required", [])

        optional_fields = ["fabricante", "capacidad_min", "capacidad_max", "tipo"]
        for field in optional_fields:
            assert field in properties, f"Missing optional property: {field}"
            assert field not in required


class TestToolParameters:
    """Tests for tool parameter schema."""

    def test_parameters_contain_required_fields(self) -> None:
        """Test parameters contain ruta_s3, categoria, fabricante, modelo."""
        result = tools.get_tool_definitions()
        tool = result[0]
        params = tool["function"]["parameters"]
        properties = params.get("properties", {})

        required_props = ["ruta_s3", "categoria", "fabricante", "modelo"]
        for prop in required_props:
            assert prop in properties, f"Missing required property: {prop}"

    def test_ruta_s3_parameter(self) -> None:
        """Test ruta_s3 parameter schema."""
        result = tools.get_tool_definitions()
        tool = result[0]
        params = tool["function"]["parameters"]
        properties = params.get("properties", {})

        ruta_s3 = properties["ruta_s3"]
        assert ruta_s3["type"] == "string"
        assert "description" in ruta_s3
        assert "S3" in ruta_s3["description"] or "s3" in ruta_s3["description"].lower()

    def test_categoria_parameter_has_enum(self) -> None:
        """Test categoria parameter has valid enum options."""
        result = tools.get_tool_definitions()
        tool = result[0]
        params = tool["function"]["parameters"]
        properties = params.get("properties", {})

        categoria = properties["categoria"]
        assert "enum" in categoria

        # Check valid enum values
        expected_categories = ["paneles", "inversores", "controladores", "baterias"]
        assert categoria["enum"] == expected_categories

    def test_fabricante_parameter(self) -> None:
        """Test fabricante parameter schema."""
        result = tools.get_tool_definitions()
        tool = result[0]
        params = tool["function"]["parameters"]
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
        params = tool["function"]["parameters"]
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
        params = tool["function"]["parameters"]

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
        function = tool.get("function", {})
        assert function.get("strict") is False


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
        ]

    def test_available_tools_constant(self) -> None:
        """Test AVAILABLE_TOOLS constant exists and contains tools."""
        assert hasattr(tools, "AVAILABLE_TOOLS")
        assert isinstance(tools.AVAILABLE_TOOLS, list)
        assert len(tools.AVAILABLE_TOOLS) > 0

    def test_leer_ficha_tecnica_tool_constant(self) -> None:
        """Test LEER_FICHA_TECNICA_TOOL constant exists."""
        assert hasattr(tools, "LEER_FICHA_TECNICA_TOOL")
        assert tools.LEER_FICHA_TECNICA_TOOL["function"]["name"] == "leer_ficha_tecnica"
