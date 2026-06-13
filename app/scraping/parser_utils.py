from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser


class Element:
    def __init__(self, tag: str, attrs: dict[str, str], text: str = "") -> None:
        self.tag = tag
        self.attrs = attrs
        self.text = text

    def attr(self, name: str) -> str | None:
        return self.attrs.get(name)


class SimpleHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[Element] = []
        self._stack: list[Element] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag=tag, attrs={key: value or "" for key, value in attrs})
        self._stack.append(element)
        self.elements.append(element)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index].tag == tag:
                self._stack.pop(index)
                break

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        for element in self._stack:
            element.text = f"{element.text} {text}".strip()


def parse_simple_html(source: str) -> list[Element]:
    parser = SimpleHtmlParser()
    parser.feed(source)
    return parser.elements


def elements_by_attr(elements: list[Element], attr: str, value: str) -> list[Element]:
    return [element for element in elements if element.attrs.get(attr) == value]


def elements_by_class(elements: list[Element], class_name: str) -> list[Element]:
    matches: list[Element] = []
    for element in elements:
        classes = element.attrs.get("class", "").split()
        if class_name in classes:
            matches.append(element)
    return matches


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", html.unescape(value)).strip()
    return normalized or None


def parse_money_cad(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"([\d\s,]+)", value)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


def parse_mileage_km(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"([\d\s,]+)\s*(?:km|kilometres|kilometers)", value, flags=re.I)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


def first_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", value)
    return int(match.group(0)) if match else None


def split_location(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) >= 2:
        return parts[0] or None, parts[1] or None
    return value.strip() or None, None


def extract_json_ld(source: str) -> list[dict]:
    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        source,
        flags=re.I | re.S,
    )
    values: list[dict] = []
    for block in blocks:
        raw_text = block.strip()
        parsed = None
        for text in (raw_text, html.unescape(raw_text)):
            try:
                parsed = json.loads(text)
                break
            except json.JSONDecodeError:
                continue
        if parsed is None:
            continue
        if isinstance(parsed, dict):
            values.append(parsed)
        elif isinstance(parsed, list):
            values.extend(item for item in parsed if isinstance(item, dict))
    return values
