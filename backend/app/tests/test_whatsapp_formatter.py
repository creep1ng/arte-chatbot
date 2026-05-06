"""Unit tests for the WhatsApp formatting filter.

Tests all 11 transformation rules, edge cases, performance budget,
and correct ordering of transformations.
"""

import time

import pytest


# ---------------------------------------------------------------------------
# Import the function under test — will fail until implementation exists
# ---------------------------------------------------------------------------
try:
    from backend.app.whatsapp_formatter import format_for_whatsapp
except ImportError:
    format_for_whatsapp = None  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def _require_formatter() -> None:
    """Skip all tests in this module if formatter not yet implemented."""
    if format_for_whatsapp is None:
        pytest.skip("backend.app.whatsapp_formatter not yet implemented")


# ===========================================================================
# Individual transformation rules
# ===========================================================================


class TestBoldConversion:
    """Rule 4: **text** → *text* (WhatsApp bold)."""

    def test_simple_bold(self) -> None:
        assert format_for_whatsapp("**bold text**") == "*bold text*"

    def test_bold_in_sentence(self) -> None:
        result = format_for_whatsapp("Los **paneles solares** son eficientes.")
        assert result == "Los *paneles solares* son eficientes."

    def test_multiple_bold(self) -> None:
        result = format_for_whatsapp("**uno** y **dos**")
        assert result == "*uno* y *dos*"


class TestItalicConversion:
    """Rule 11: _text_ preserved; single *text* → _text_."""

    def test_underscore_italic_preserved(self) -> None:
        assert format_for_whatsapp("_italic_") == "_italic_"

    def test_single_star_italic(self) -> None:
        result = format_for_whatsapp("*italic*")
        assert result == "_italic_"


class TestStrikethroughConversion:
    """Rule 5: ~~text~~ → ~text~."""

    def test_simple_strikethrough(self) -> None:
        assert format_for_whatsapp("~~deleted~~") == "~deleted~"

    def test_strikethrough_in_sentence(self) -> None:
        result = format_for_whatsapp("Esto es ~~incorrecto~~ correcto.")
        assert result == "Esto es ~incorrecto~ correcto."


class TestHeadingConversion:
    """Rule 3: # text / ## text / ### text → *text*."""

    def test_h1(self) -> None:
        assert format_for_whatsapp("# Título") == "*Título*"

    def test_h2(self) -> None:
        assert format_for_whatsapp("## Subtítulo") == "*Subtítulo*"

    def test_h3(self) -> None:
        assert format_for_whatsapp("### Sección") == "*Sección*"

    def test_heading_with_content_after(self) -> None:
        result = format_for_whatsapp("## Productos\n\nContenido aquí")
        assert result == "*Productos*\n\nContenido aquí"


class TestUnorderedListConversion:
    """Rule 9: - item / * item → • item."""

    def test_dash_list(self) -> None:
        result = format_for_whatsapp("- Panel\n- Inversor\n- Batería")
        assert result == "• Panel\n• Inversor\n• Batería"

    def test_star_list(self) -> None:
        result = format_for_whatsapp("* Item uno\n* Item dos")
        assert result == "• Item uno\n• Item dos"


class TestOrderedListConversion:
    """Rule 10: 1. item → emoji numbering."""

    def test_single_digit_list(self) -> None:
        result = format_for_whatsapp("1. Primero\n2. Segundo\n3. Tercero")
        assert result == "1️⃣ Primero\n2️⃣ Segundo\n3️⃣ Tercero"

    def test_double_digit_fallback(self) -> None:
        """Items 10+ use N. format."""
        result = format_for_whatsapp("10. Décimo")
        assert result == "10. Décimo"


class TestLinkConversion:
    """Rule 6: [text](url) → text (strip URL)."""

    def test_simple_link(self) -> None:
        result = format_for_whatsapp("[ficha técnica](https://example.com/file.pdf)")
        assert result == "ficha técnica"

    def test_multiple_links(self) -> None:
        result = format_for_whatsapp(
            "Ver [catálogo](https://a.com) y [precios](https://b.com)"
        )
        assert result == "Ver catálogo y precios"

    def test_bare_url_preserved(self) -> None:
        """URLs without bracket syntax are preserved unchanged."""
        result = format_for_whatsapp("Visita https://arte.com/catalogo")
        assert result == "Visita https://arte.com/catalogo"


class TestInlineCodeConversion:
    """Rule 2: `code` → code (strip backticks)."""

    def test_simple_inline_code(self) -> None:
        assert format_for_whatsapp("`code`") == "code"

    def test_inline_code_in_sentence(self) -> None:
        result = format_for_whatsapp("Usa el comando `pip install`.")
        assert result == "Usa el comando pip install."


class TestCodeBlockConversion:
    """Rule 1: ```lang\ncode\n``` → code (strip fences)."""

    def test_fenced_code_block(self) -> None:
        md = "```python\nprint('hello')\n```"
        result = format_for_whatsapp(md)
        assert "```" not in result
        assert "print('hello')" in result

    def test_code_block_without_language(self) -> None:
        md = "```\ncode here\n```"
        result = format_for_whatsapp(md)
        assert "```" not in result
        assert "code here" in result


class TestHorizontalRuleRemoval:
    """Rule 10: --- / *** → remove."""

    def test_dash_rule(self) -> None:
        result = format_for_whatsapp("antes\n---\ndespués")
        assert "---" not in result

    def test_star_rule(self) -> None:
        result = format_for_whatsapp("antes\n***\ndespués")
        assert "***" not in result


class TestBlockquoteConversion:
    """Rule 8: > text → text (strip >)."""

    def test_simple_blockquote(self) -> None:
        result = format_for_whatsapp("> Esto es una cita")
        assert result == "Esto es una cita"

    def test_blockquote_with_content(self) -> None:
        result = format_for_whatsapp("Antes\n> Cita\nDespués")
        assert "> " not in result
        assert "Cita" in result


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases: empty, nested, emoji, multi-paragraph."""

    def test_empty_string(self) -> None:
        assert format_for_whatsapp("") == ""

    def test_plain_text_passthrough(self) -> None:
        """Text without markdown passes through unchanged."""
        text = "Hola, ¿cómo estás?"
        assert format_for_whatsapp(text) == text

    def test_emoji_preserved(self) -> None:
        text = "☀️ Los paneles solares son 🌞"
        assert format_for_whatsapp(text) == text

    def test_multi_paragraph_preserved(self) -> None:
        text = "Primer párrafo.\n\nSegundo párrafo."
        result = format_for_whatsapp(text)
        assert "\n\n" in result
        assert "Primer párrafo." in result
        assert "Segundo párrafo." in result

    def test_nested_bold_italic(self) -> None:
        """Nested markdown: **bold _and italic_** should still transform."""
        result = format_for_whatsapp("**bold _and italic_**")
        assert "*bold _and italic_*" == result


# ===========================================================================
# Correct transformation order
# ===========================================================================


class TestTransformationOrder:
    """Verify transformations are applied in the correct order.

    Code blocks must be processed BEFORE inline code to prevent
    backtick stripping inside fenced code blocks.
    """

    def test_code_block_before_inline_code(self) -> None:
        """Fenced code block backticks must be stripped, not treated as inline."""
        md = "```\n`inner`\n```"
        result = format_for_whatsapp(md)
        # The fenced block should be stripped; inner backtick should survive
        # because it's inside the code block content, not inline code
        assert "```" not in result

    def test_bold_before_italic(self) -> None:
        """Bold markers processed before italic to avoid conflict with *."""
        result = format_for_whatsapp("**bold** and *italic*")
        assert result == "*bold* and _italic_"


# ===========================================================================
# Performance
# ===========================================================================


class TestPerformance:
    """Performance: < 5ms for 10k characters."""

    def test_performance_10k_chars(self) -> None:
        """Must complete within 5ms for a 10,000-char mixed-markdown string."""
        # Build a 10k-char string with mixed markdown
        segment = "## Heading\n**bold** _italic_ `code`\n- item\n"
        repeat_count = 10000 // len(segment) + 1
        text = (segment * repeat_count)[:10000]

        start = time.perf_counter()
        result = format_for_whatsapp(text)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 5.0, f"Formatting took {elapsed_ms:.2f}ms (budget: 5ms)"
        # Sanity: no raw markdown fences remain
        assert "```" not in result
