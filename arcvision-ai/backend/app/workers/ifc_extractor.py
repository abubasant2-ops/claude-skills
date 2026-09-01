"""IFC extractor — IfcOpenShell deterministic extraction.

For each element we capture:
  - element_type (mapped to UEM)
  - discipline
  - geometry: length/area/volume/thickness/count derived from BaseQuantities first,
    falling back to ifcopenshell.geom for bounding-box derived metrics.
  - source_ref: ifc_guid + ifc_type
  - confidence: 0.95 when BaseQuantities present, 0.85 when geometry-derived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.element as ifc_el_util
    _IFC_AVAILABLE = True
except Exception:  # pragma: no cover
    _IFC_AVAILABLE = False


# (IfcType → UEM element_type, discipline)
_TYPE_MAP: dict[str, tuple[str, str]] = {
    "IfcWall": ("wall", "arch"),
    "IfcWallStandardCase": ("wall", "arch"),
    "IfcSlab": ("slab", "struct"),
    "IfcColumn": ("column", "struct"),
    "IfcBeam": ("beam", "struct"),
    "IfcFooting": ("footing", "struct"),
    "IfcDoor": ("door", "arch"),
    "IfcWindow": ("window", "arch"),
    "IfcSpace": ("space", "arch"),
    "IfcCableSegment": ("cable", "elec"),
    "IfcPipeSegment": ("pipe", "plumb"),
    "IfcUnitaryEquipment": ("hvac_unit", "mech"),
}

# Map IFC Qto property names → our geometry fields.
_QTO_FIELD_MAP: dict[str, str] = {
    "Length": "length_m",
    "Width": "width_m",
    "Height": "height_m",
    "GrossArea": "area_m2",
    "NetArea": "area_m2",
    "GrossSideArea": "area_m2",
    "NetSideArea": "area_m2",
    "GrossFootprintArea": "area_m2",
    "GrossVolume": "volume_m3",
    "NetVolume": "volume_m3",
    "Thickness": "thickness_m",
}


@dataclass
class ExtractedIfcElement:
    element_type: str
    discipline: str
    geometry: dict[str, Any] = field(default_factory=dict)
    source_ref: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.95
    extraction_method: str = "ifc"


def _extract_qtos(el: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    try:
        psets = ifc_el_util.get_psets(el, qtos_only=True)
    except Exception:
        return out
    for _qto_name, props in (psets or {}).items():
        if not isinstance(props, dict):
            continue
        for k, v in props.items():
            if k in _QTO_FIELD_MAP and isinstance(v, (int, float)):
                # Keep the larger value if multiple Qtos report the same field.
                existing = out.get(_QTO_FIELD_MAP[k])
                if existing is None or float(v) > existing:
                    out[_QTO_FIELD_MAP[k]] = float(v)
    return out


def _bbox_geometry(el: Any) -> dict[str, float]:
    """Fallback: derive coarse geometry from the shape bounding box."""
    try:
        settings_ = ifcopenshell.geom.settings()
        settings_.set(settings_.USE_WORLD_COORDS, True)
        shape = ifcopenshell.geom.create_shape(settings_, el)
        verts = shape.geometry.verts  # flat [x,y,z, x,y,z, ...]
        if not verts:
            return {}
        xs = verts[0::3]
        ys = verts[1::3]
        zs = verts[2::3]
        dx = max(xs) - min(xs)
        dy = max(ys) - min(ys)
        dz = max(zs) - min(zs)
        out: dict[str, float] = {
            "length_m": max(dx, dy),
            "width_m": min(dx, dy),
            "height_m": dz,
        }
        # crude volume / area
        out["volume_m3"] = dx * dy * dz
        # the largest face area, useful for slabs / walls
        out["area_m2"] = max(dx * dy, dx * dz, dy * dz)
        return out
    except Exception:
        return {}


def extract_elements(ifc_path: str) -> list[ExtractedIfcElement]:
    if not _IFC_AVAILABLE:
        raise RuntimeError("ifcopenshell not installed in this environment")

    model = ifcopenshell.open(ifc_path)
    results: list[ExtractedIfcElement] = []

    for ifc_type, (uem_type, discipline) in _TYPE_MAP.items():
        try:
            elements = model.by_type(ifc_type)
        except Exception:
            continue
        for el in elements:
            qtos = _extract_qtos(el)
            confidence = 0.95
            if not qtos:
                qtos = _bbox_geometry(el)
                confidence = 0.85
            if not qtos:
                # nothing usable
                continue
            results.append(
                ExtractedIfcElement(
                    element_type=uem_type,
                    discipline=discipline,
                    geometry=qtos,
                    source_ref={"ifc_guid": getattr(el, "GlobalId", None), "ifc_type": ifc_type},
                    confidence=confidence,
                )
            )
    return results
