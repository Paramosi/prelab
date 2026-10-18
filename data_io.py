"""Strict CSV catalog loading and source-preserving exports. No CSV evaluation."""

import csv
from dataclasses import asdict, fields
from hashlib import sha256
import io
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
    
import numpy as np

from domain import Catalog, Material, Point, Provenance, ValidationError, MODEL_VERSION, validate_material


CATALOG_FILES = ("materials.csv", "curve_points.csv", "provenance.csv")
MAX_CATALOG_BYTES = 5_000_000
FLOAT_FIELDS = {"E_MPa", "yield_MPa", "uts_MPa", "elongation_fraction", "offset_strain",
                "exponent", "fracture_strain", "fracture_stress_MPa", "strain_at_uts", "localization_strain"}
OPTIONAL_FLOATS = {"yield_MPa", "localization_strain"}


def _rows(blob: bytes, schema: list[str], name: str) -> list[dict[str, str]]:
    if len(blob) > MAX_CATALOG_BYTES:
        raise ValidationError(f"{name}: catalog file is too large.")
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{name}: save the file as UTF-8 CSV.") from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or set(header) != set(schema):
            missing, extra = set(schema) - set(header), set(header) - set(schema)
            raise ValidationError(f"{name}: invalid header. Missing: {sorted(missing)}; extra: {sorted(extra)}. Use the catalog template.")
        rows = []
        for number, row in enumerate(reader, start=2):
            if None in row or any(v is None for v in row.values()):
                raise ValidationError(f"{name}, row {number}: incorrect number of columns.")
            rows.append({k: v.strip() for k, v in row.items()})
            if len(rows) > 10000:
                raise ValidationError(f"{name}: more than 10,000 rows are not supported.")
        return rows
    except csv.Error as exc:
        raise ValidationError(f"{name}: malformed CSV: {exc}") from exc


def _number(value: str, field: str, optional: bool = False):
    if not value and optional:
        return None
    try:
        result = float(value)
    except ValueError as exc:
        raise ValidationError(f"{field}: expected a numeric value, not {value!r}.") from exc
    if not np.isfinite(result):
        raise ValidationError(f"{field}: NaN and infinity are not accepted.")
    return result


def load_catalog(files: dict[str, bytes]) -> Catalog:
    if set(files) != set(CATALOG_FILES):
        raise ValidationError("A catalog must contain materials.csv, curve_points.csv, and provenance.csv.")
    materials = {}
    for row in _rows(files["materials.csv"], [f.name for f in fields(Material)], "materials.csv"):
        for key in FLOAT_FIELDS:
            row[key] = _number(row[key], f"{row['variant_id']}.{key}", key in OPTIONAL_FLOATS)
        for key in ("q2", "q3", "q4"):
            if row[key].lower() not in {"true", "false"}:
                raise ValidationError(f"{row['variant_id']}.{key}: use true or false.")
            row[key] = row[key].lower() == "true"
        m = Material(**row)
        validate_material(m)
        if m.variant_id in materials:
            raise ValidationError(f"Duplicate material ID: {m.variant_id}.")
        materials[m.variant_id] = m
    if not materials:
        raise ValidationError("The catalog has no materials.")
    if len(materials) > 100:
        raise ValidationError("A catalog may contain at most 100 datasets.")
    for m in materials.values():
        if m.parent_variant_id and m.parent_variant_id not in materials:
            raise ValidationError(f"{m.variant_id}: parent dataset does not exist.")
        chain = {m.variant_id}
        parent = m.parent_variant_id
        while parent:
            if parent in chain:
                raise ValidationError(f"{m.variant_id}: cyclic dataset ancestry.")
            chain.add(parent)
            parent = materials[parent].parent_variant_id
    points = {key: [] for key in materials}
    point_keys = set()
    for row in _rows(files["curve_points.csv"], [f.name for f in fields(Point)], "curve_points.csv"):
        if row["variant_id"] not in materials:
            raise ValidationError("An anchor references an unknown material ID.")
        key = (row["variant_id"], row["point_id"])
        if key in point_keys or not row["point_id"]:
            raise ValidationError("Anchor IDs must be nonempty and unique within a material.")
        point_keys.add(key)
        for name in ("strain", "stress_MPa", "tangent_MPa"):
            row[name] = _number(row[name], f"{key}.{name}", name == "tangent_MPa")
        points[row["variant_id"]].append(Point(**row))
    provenance = []
    seen_sources = set()
    for row in _rows(files["provenance.csv"], [f.name for f in fields(Provenance)], "provenance.csv"):
        if row["variant_id"] not in materials or row["kind"] not in {"reported", "derived", "assumed"}:
            raise ValidationError("A source has an unknown ID or value kind.")
        if not row["source_title"] or not row["source_locator"] or not row["field"]:
            raise ValidationError("Each source record requires a field, document title, and locator.")
        if row["kind"] != "reported" and not row["derivation"]:
            raise ValidationError("Derived and assumed records require an explanation.")
        key = (row["variant_id"], row["field"])
        if key in seen_sources:
            raise ValidationError(f"Duplicate source record: {key}.")
        seen_sources.add(key)
        provenance.append(Provenance(**row))
    required = {"E_MPa", "uts_MPa", "elongation_fraction", "fracture_strain", "fracture_stress_MPa",
                "strain_at_uts", "model_id", "geometry_mode", "exponent", "offset_strain"}
    for key, m in materials.items():
        needed = required | ({"yield_MPa"} if m.yield_MPa is not None else set())
        if m.localization_strain is not None:
            needed.add("localization_strain")
        needed.update(f"points.{p.point_id}" for p in points[key])
        missing = sorted(f for f in needed if (key, f) not in seen_sources)
        if missing:
            raise ValidationError(f"{key}: missing provenance for {', '.join(missing)}.")
    digest = sha256()
    for name in sorted(files):
        digest.update(name.encode())
        digest.update(files[name])
    return Catalog(materials, {k: tuple(v) for k, v in points.items()}, tuple(provenance), digest.hexdigest(), dict(files))


def read_catalog(directory: Path) -> Catalog:
    try:
        return load_catalog({name: (directory / name).read_bytes() for name in CATALOG_FILES})
    except OSError as exc:
        raise ValidationError(f"Could not read the catalog: {exc}") from exc


def read_catalog_zip(blob: bytes) -> Catalog:
    if len(blob) > MAX_CATALOG_BYTES:
        raise ValidationError("The catalog archive is too large.")
    try:
        with ZipFile(io.BytesIO(blob)) as z:
            names = z.namelist()
            if len(names) != 3 or set(names) != set(CATALOG_FILES):
                raise ValidationError("The ZIP must contain exactly the three catalog CSV files at its root.")
            if sum(info.file_size for info in z.infolist()) > MAX_CATALOG_BYTES:
                raise ValidationError("The uncompressed catalog is too large.")
            return load_catalog({name: z.read(name) for name in CATALOG_FILES})
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("This file is not a readable catalog ZIP.") from exc


def _zip(files: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with ZipFile(out, "w", ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()


def catalog_zip(catalog: Catalog) -> bytes:
    return _zip(catalog.files)


def csv_bytes(rows: list[dict], headers: list[str]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def export_results(results: dict, catalog: Catalog) -> tuple[bytes, bytes]:
    """Return selected curve CSV and a ZIP with exact inputs and provenance."""
    selected = set(results)
    rows = []
    for key, result in results.items():
        for e, s, stage in zip(result.strain, result.stress_MPa, result.stages):
            rows.append({"variant_id": key, "material": result.material.material_name,
                         "condition": result.material.condition, "engineering_strain": format(float(e), ".16g"),
                         "engineering_stress_MPa": format(float(s), ".16g"), "stage": stage})
    curves = csv_bytes(rows, ["variant_id", "material", "condition", "engineering_strain", "engineering_stress_MPa", "stage"])
    metadata = {
        "model_version": MODEL_VERSION, "catalog_sha256": catalog.fingerprint,
        "selected_ids": list(results), "units": {"stress": "MPa", "strain": "fraction"},
        "interpretation": "Lecture properties with explicit illustrative shape assumptions; not measured full curves.",
        "materials": [asdict(r.material) for r in results.values()],
        "anchors": [asdict(p) for key in results for p in catalog.points[key]],
        "provenance": [asdict(p) for p in catalog.provenance if p.variant_id in selected],
        "metrics": {key: {"work_density_MJ_m3": r.work_density_MJ_m3,
                           "sample_count": len(r.strain), "events": r.model.events}
                    for key, r in results.items()},
    }
    selected_sources = [asdict(p) for p in catalog.provenance if p.variant_id in selected]
    package = _zip({"curves.csv": curves,
                    "metadata.json": json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                    "provenance.csv": csv_bytes(selected_sources, [f.name for f in fields(Provenance)])})
    return curves, package

