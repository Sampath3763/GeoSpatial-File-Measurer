"""PDF survey measurement report generator.

Generates a printable measurement certificate using fpdf2 (pure-Python,
LGPL-licensed).  No FastAPI, SQLite, or network dependencies.
"""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF, XPos, YPos

_PAGE_MARGIN = 15
_LINE_H = 7
_SECTION_GAP = 5
_HEADER_COLOR = (30, 60, 120)
_ACCENT_COLOR = (0, 120, 200)
_ROW_ALT_COLOR = (245, 248, 252)
_TEXT_COLOR = (30, 30, 30)
_MUTED_COLOR = (100, 100, 110)
_MAX_TABLE_FEATURES = 15


class _GeoReportPDF(FPDF):
    """Custom FPDF subclass with a branded header and page footer."""

    def __init__(self, filename: str, generated_at: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self._filename = filename
        self._generated_at = generated_at
        self.set_margins(_PAGE_MARGIN, _PAGE_MARGIN, _PAGE_MARGIN)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:
        self.set_fill_color(*_HEADER_COLOR)
        self.rect(0, 0, 210, 18, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 11)
        self.set_xy(_PAGE_MARGIN, 5)
        self.cell(0, 8, "Geospatial File Measurement Certificate", align="L")
        self.set_font("Helvetica", "", 8)
        self.set_xy(_PAGE_MARGIN, 5)
        self.cell(0, 8, f"Generated: {self._generated_at}", align="R")
        self.ln(14)
        self.set_text_color(*_TEXT_COLOR)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*_MUTED_COLOR)
        self.cell(0, 5, f"Page {self.page_no()} | {self._filename}", align="C")
        self.set_text_color(*_TEXT_COLOR)

    def section_title(self, title: str) -> None:
        """Render a coloured section heading with underline rule."""
        self.ln(_SECTION_GAP)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*_ACCENT_COLOR)
        self.cell(0, 7, title.upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*_ACCENT_COLOR)
        self.set_line_width(0.3)
        lm = self.l_margin
        self.line(lm, self.get_y(), 210 - lm, self.get_y())
        self.ln(2)
        self.set_text_color(*_TEXT_COLOR)
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.2)

    def kv_row(self, key: str, value: str, bold_value: bool = False) -> None:
        """Render a key: value info row."""
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*_MUTED_COLOR)
        self.cell(55, _LINE_H, key, new_x=XPos.RIGHT)
        self.set_text_color(*_TEXT_COLOR)
        self.set_font("Helvetica", "B" if bold_value else "", 9)
        self.cell(0, _LINE_H, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def table_header(self, cols: list[tuple[str, int]]) -> None:
        """Render a shaded table header row."""
        self.set_fill_color(*_HEADER_COLOR)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8)
        for label, width in cols:
            self.cell(width, 6, label, border=0, fill=True, align="C")
        self.ln()
        self.set_text_color(*_TEXT_COLOR)

    def table_row(
        self,
        values: list[str],
        cols: list[tuple[str, int]],
        alt: bool,
    ) -> None:
        """Render an alternating-colour data row."""
        self.set_fill_color(*(_ROW_ALT_COLOR if alt else (255, 255, 255)))
        self.set_font("Helvetica", "", 8)
        for value, (_, width) in zip(values, cols, strict=False):
            self.cell(width, 6, value, border=0, fill=True, align="C")
        self.ln()


def generate_pdf_report(
    file_doc: dict[str, Any],
    summary: dict[str, Any],
    top_features: list[dict[str, Any]],
    sha256_hash: str | None = None,
) -> bytes:
    """Build and return the PDF measurement certificate as raw bytes.

    Parameters
    ----------
    file_doc:
        Stored file metadata document from the repository.
    summary:
        Aggregate measurement summary (total_area_sq_m, total_length_m, etc.).
    top_features:
        Up to ``_MAX_TABLE_FEATURES`` feature dicts sorted by area descending.
    sha256_hash:
        Optional SHA-256 of the original uploaded binary.
    """
    from app.services.unit_conversion import (
        AreaUnit,
        LengthUnit,
        area_label,
        convert_area,
        convert_length,
        length_label,
    )

    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    filename = file_doc.get("filename", "unknown")

    pdf = _GeoReportPDF(filename=filename, generated_at=generated_at)
    pdf.add_page()

    # 1. Project metadata
    pdf.section_title("1. Project Details")
    pdf.kv_row("File Name", filename, bold_value=True)
    pdf.kv_row("File Type", str(file_doc.get("file_type", "")).upper())
    pdf.kv_row("File ID", str(file_doc.get("id", "")))
    pdf.kv_row("Upload Time", str(file_doc.get("created_at", "")))
    pdf.kv_row("Processing Status", str(file_doc.get("status", "")))
    pdf.kv_row("Feature Count", str(file_doc.get("feature_count", 0)))
    pdf.kv_row("SHA-256 Hash", sha256_hash or "N/A")

    # 2. CRS audit
    pdf.section_title("2. Coordinate Reference System (CRS) Audit")
    pdf.kv_row("Source CRS (declared)", file_doc.get("crs") or "Not detected")
    pdf.kv_row("Measurement Projection", "Auto-selected UTM / Equal-Area / UPS")
    pdf.kv_row("Datum", "WGS 84")

    # 3. Aggregate measurement summary
    pdf.section_title("3. Measurement Summary")
    total_area_sq_m: float = summary.get("total_area_sq_m", 0.0)
    total_length_m: float = summary.get("total_length_m", 0.0)

    area_units = [AreaUnit.SQ_M, AreaUnit.HECTARES, AreaUnit.ACRES, AreaUnit.SQ_KM]
    area_conv = convert_area(total_area_sq_m, area_units)
    length_units = [LengthUnit.M, LengthUnit.KM, LengthUnit.MI]
    length_conv = convert_length(total_length_m, length_units)

    pdf.kv_row(
        "Total Area",
        " | ".join(
            f"{v:,.4f} {area_label(u)}"
            for u, v in zip(area_units, area_conv.values.values(), strict=False)
        ),
        bold_value=True,
    )
    pdf.kv_row(
        "Total Length",
        " | ".join(
            f"{v:,.4f} {length_label(u)}"
            for u, v in zip(length_units, length_conv.values.values(), strict=False)
        ),
        bold_value=True,
    )

    for geom_type, count in summary.get("counts_by_geometry_type", {}).items():
        pdf.kv_row(f"  {geom_type} count", str(count))

    for status, count in summary.get("counts_by_measurement_status", {}).items():
        pdf.kv_row(f"  Status: {status}", str(count))

    # 4. Top features table
    pdf.section_title("4. Top Features by Area (sq m)")
    top = top_features[:_MAX_TABLE_FEATURES]
    if top:
        cols: list[tuple[str, int]] = [
            ("#", 12),
            ("Layer", 30),
            ("Geometry Type", 35),
            ("Area (sq m)", 38),
            ("Area (ha)", 30),
            ("Area (ac)", 30),
        ]
        pdf.table_header(cols)
        for row_idx, feat in enumerate(top):
            area_m2 = feat.get("area_sq_m") or 0.0
            ha = round(area_m2 / 10_000, 4)
            ac = round(area_m2 * 2.471_053_815e-4, 4)
            pdf.table_row(
                [
                    str(feat.get("feature_index", row_idx + 1)),
                    str(feat.get("layer") or "-")[:18],
                    str(feat.get("geometry_type", ""))[:18],
                    f"{area_m2:,.2f}",
                    f"{ha:,.4f}",
                    f"{ac:,.4f}",
                ],
                cols,
                alt=row_idx % 2 == 1,
            )
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_MUTED_COLOR)
        pdf.cell(
            0,
            _LINE_H,
            "No polygon features with calculated measurements.",
            new_y=YPos.NEXT,
        )
        pdf.set_text_color(*_TEXT_COLOR)

    # Disclaimer note
    pdf.ln(_SECTION_GAP)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*_MUTED_COLOR)
    pdf.multi_cell(
        0,
        5,
        (
            "Note: All area and length values are calculated using an auto-selected "
            "projected CRS (UTM / LAEA / UPS) for maximum accuracy. "
            "Results represent the best available estimate given the source data quality."
        ),
    )

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def compute_sha256(content: bytes) -> str:
    """Return the hex-encoded SHA-256 digest of content."""
    return hashlib.sha256(content).hexdigest()
