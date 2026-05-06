"""WhatsApp formatting filter — pure function module.

Transforms raw LLM markdown output into WhatsApp-compatible text.
11 regex-based transformation rules applied in a specific order to
avoid conflicts (e.g., code blocks before inline code).

Dependencies: None (stdlib `re` only).
Performance: < 5ms for 10,000 characters.
"""

import re

# Emoji numbers for ordered lists (1-9)
_EMOJI_NUMBERS: list[str] = [
    "1️⃣",
    "2️⃣",
    "3️⃣",
    "4️⃣",
    "5️⃣",
    "6️⃣",
    "7️⃣",
    "8️⃣",
    "9️⃣",
]

# Pre-compiled regexes in transformation order
_RE_CODE_BLOCKS = re.compile(r"```(?:\w*\n)?(.*?)```", re.DOTALL)
_RE_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_RE_HEADINGS = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)
_RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RE_STRIKETHROUGH = re.compile(r"~~(.+?)~~")
_RE_LINKS = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RE_HORIZONTAL_RULES = re.compile(r"^[-*]{3,}\s*$", re.MULTILINE)
_RE_BLOCKQUOTES = re.compile(r"^>\s?(.+)$", re.MULTILINE)
_RE_UNORDERED_LISTS = re.compile(r"^[\-\*]\s+(.+)$", re.MULTILINE)
_RE_ORDERED_LISTS = re.compile(r"^(\d+)\.\s+(.+)$", re.MULTILINE)
_RE_SINGLE_STAR_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def format_for_whatsapp(text: str) -> str:
    """Transform raw LLM markdown output into WhatsApp-compatible text.

    Applies 11 regex-based rules in a specific order to avoid conflicts.
    This is a pure function with no side effects.

    Args:
        text: Raw LLM output with markdown formatting.

    Returns:
        WhatsApp-compatible string.

    Performance: < 5ms for 10,000 characters (regex-only, no external deps).
    """
    if not text:
        return ""

    # 1. Code blocks → strip fences and language tag, keep code
    text = _RE_CODE_BLOCKS.sub(r"\1", text)

    # 2. Inline code → strip backticks
    text = _RE_INLINE_CODE.sub(r"\1", text)

    # 3. Italic *text* (single star) → _text_
    #    MUST run before bold and headings, which produce *text* output
    text = _RE_SINGLE_STAR_ITALIC.sub(r"_\1_", text)

    # 4. Headings → *text* (WhatsApp bold)
    text = _RE_HEADINGS.sub(r"*\1*", text)

    # 5. Bold **text** → *text*
    text = _RE_BOLD.sub(r"*\1*", text)

    # 6. Strikethrough ~~text~~ → ~text~
    text = _RE_STRIKETHROUGH.sub(r"~\1~", text)

    # 7. Links [text](url) → text (strip URL)
    text = _RE_LINKS.sub(r"\1", text)

    # 8. Horizontal rules → remove line
    text = _RE_HORIZONTAL_RULES.sub("", text)

    # 9. Blockquotes > text → text
    text = _RE_BLOCKQUOTES.sub(r"\1", text)

    # 10. Unordered lists - item / * item → • item
    text = _RE_UNORDERED_LISTS.sub(r"• \1", text)

    # 11. Ordered lists 1. item → emoji numbering
    def _replace_ordered(match: re.Match[str]) -> str:
        num = int(match.group(1))
        content = match.group(2)
        if 1 <= num <= 9:
            return f"{_EMOJI_NUMBERS[num - 1]} {content}"
        return f"{num}. {content}"

    text = _RE_ORDERED_LISTS.sub(_replace_ordered, text)

    # Clean up excessive blank lines left by removed elements
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
