"""
Taxonomy loading.

Parses the StoryScope 304-feature taxonomy (10 NarraBench dimensions,
~18 aspects per dimension). Structure ported from the paper's
`storyscope.5_feature_application.apply_features` module (MIT).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class Feature:
    id: str
    name: str
    question: str
    type: str  # categorical | ordinal | scale | binary | multi_select
    values: List[str]
    condition: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "question": self.question,
            "type": self.type,
            "values": self.values,
            "condition": self.condition,
        }


@dataclass
class Dimension:
    key: str
    name: str
    description: str
    features: List[Feature] = field(default_factory=list)


class Taxonomy:
    def __init__(self, dimensions: List[Dimension]):
        self.dimensions = dimensions
        self._by_id: Dict[str, Feature] = {
            f.id: f for d in dimensions for f in d.features
        }

    @property
    def total_features(self) -> int:
        return len(self._by_id)

    def feature(self, fid: str) -> Feature:
        return self._by_id[fid]

    def feature_ids(self) -> List[str]:
        """Ordered feature IDs, in taxonomy order (matches training order)."""
        return [f.id for d in self.dimensions for f in d.features]

    def dimension_for(self, fid: str) -> Dimension:
        for d in self.dimensions:
            if fid in d._feature_ids:
                return d
        raise KeyError(fid)

    @classmethod
    def from_json(cls, path: str | Path) -> "Taxonomy":
        with open(path) as f:
            data = json.load(f)
        feature_data = data.get("feature_taxonomy", data)
        dimensions: List[Dimension] = []
        for dim_key, dim_data in feature_data.items():
            if dim_key in ("taxonomy_metadata", "feature_index"):
                continue
            if not isinstance(dim_data, dict):
                continue
            dim = Dimension(
                key=dim_key,
                name=dim_data.get("dimension_name", dim_key),
                description=dim_data.get("dimension_description", ""),
            )
            for aspect_data in dim_data.get("aspects", {}).values():
                for feat_data in aspect_data.get("features", []):
                    dim.features.append(Feature(
                        id=feat_data["id"],
                        name=feat_data.get("name", feat_data["id"]),
                        question=feat_data.get("question", ""),
                        type=feat_data.get("type", "categorical"),
                        values=list(feat_data.get("values", [])),
                        condition=feat_data.get("condition"),
                    ))
            dim._feature_ids = [f.id for f in dim.features]
            if dim.features:
                dimensions.append(dim)
        return cls(dimensions)
