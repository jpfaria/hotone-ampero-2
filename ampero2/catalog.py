"""Model catalog (from the editor's bundled table, see catalog_build.py): names, codes, parameters."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name("catalog.json")


@dataclass(frozen=True)
class Param:
    index: int
    name: str
    default: str
    min: str
    max: str
    type: str


@dataclass(frozen=True)
class Model:
    category: str
    category_index: int
    index: int
    name: str
    code: int
    based_on: str | None
    params: tuple[Param, ...]


@dataclass(frozen=True)
class Category:
    index: int
    name: str
    models: tuple[Model, ...]


class Catalog:
    def __init__(self, categories: list[Category]):
        self.categories = categories
        self._by_code = {m.code: m for c in categories for m in c.models}

    @classmethod
    def load(cls, path: Path = CATALOG_PATH) -> "Catalog":
        data = json.loads(path.read_text())
        cats = []
        for c in data["categories"]:
            models = tuple(
                Model(c["name"], c["index"], m["index"], m["name"], m["code"], m.get("based_on"),
                      tuple(Param(int(p["ID"]), p["Name"], p.get("DefaultValue", ""), p.get("DisplayMin", ""),
                                  p.get("DisplayMax", ""), p.get("Type", "")) for p in m["params"]))
                for m in c["models"])
            cats.append(Category(c["index"], c["name"], models))
        return cls(cats)

    def category(self, name: str) -> Category:
        for c in self.categories:
            if c.name.lower() == name.lower():
                return c
        raise KeyError(f"unknown category {name!r}")

    def find(self, category: str, model: str) -> Model:
        cat = self.category(category)
        for m in cat.models:
            if m.name.lower() == model.lower():
                return m
        raise KeyError(f"unknown model {model!r} in {cat.name}")

    def by_code(self, code: int) -> Model:
        return self._by_code[code]
