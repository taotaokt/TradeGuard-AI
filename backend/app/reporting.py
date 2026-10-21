import json
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.app.models import Assessment


NAVY = colors.HexColor("#132A3A")
TEAL = colors.HexColor("#087E8B")
PALE = colors.HexColor("#EEF5F5")
MUTED = colors.HexColor("#53656F")


def _safe_json(raw: str, fallback):
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _footer(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D9E3E7"))
    canvas.line(document.leftMargin, 0.54 * inch, letter[0] - document.rightMargin, 0.54 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(document.leftMargin, 0.36 * inch, "TradeGuard AI - decision support report")
    canvas.drawRightString(
        letter[0] - document.rightMargin, 0.36 * inch, "Page {}".format(document.page)
    )
    canvas.restoreState()


def build_assessment_pdf(assessment: Assessment) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.72 * inch,
        title="TradeGuard AI Assessment Report",
        author="TradeGuard AI",
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            textColor=NAVY,
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=25,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            textColor=NAVY,
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            spaceBefore=14,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["BodyText"],
            textColor=MUTED,
            fontSize=8.5,
            leading=11,
        )
    )
    normal = styles["BodyText"]
    normal.fontSize = 9.5
    normal.leading = 13

    snapshot = _safe_json(assessment.input_snapshot_json, {})
    decision = assessment.decision
    prediction = assessment.prediction
    risk_dimensions = _safe_json(decision.risk_dimensions_json, {}) if decision else {}
    reasons = _safe_json(decision.reason_codes_json, []) if decision else []

    story = [
        Paragraph("TRADEGUARD AI", styles["Small"]),
        Paragraph("Assessment Report", styles["ReportTitle"]),
        Paragraph(
            "Explainable cross-border transaction risk decision support", styles["Small"]
        ),
        Spacer(1, 0.15 * inch),
    ]
    summary_rows = [
        ["Reference", snapshot.get("reference", "-")],
        ["Assessment", "v{} / {}".format(assessment.version, assessment.id)],
        ["Generated from", assessment.completed_at.isoformat() + "Z" if assessment.completed_at else "In progress"],
        ["Recommendation", assessment.recommendation or "Pending"],
        ["Workflow status", assessment.status],
    ]
    summary = Table(summary_rows, colWidths=[1.35 * inch, 5.55 * inch])
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), PALE),
                ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E3E7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([summary, Paragraph("Transaction", styles["Section"])])
    transaction_rows = [
        ["Product", snapshot.get("product_description", "-")],
        ["Route", "{} to {}".format(snapshot.get("origin_country", "-"), snapshot.get("destination_country", "-"))],
        ["Amount", "{} {}".format(snapshot.get("currency", ""), snapshot.get("amount", "-"))],
        ["Payment", "{} / {} days / {}% deposit".format(snapshot.get("payment_method", "-"), snapshot.get("payment_terms_days", "-"), snapshot.get("deposit_percentage", "-"))],
        ["End use", snapshot.get("end_use", "-")],
    ]
    detail = Table(transaction_rows, colWidths=[1.35 * inch, 5.55 * inch])
    detail.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
                ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E9EC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([detail, Paragraph("Risk overview", styles["Section"])])
    risk_rows = [["Dimension", "Result"]] + [
        [name.replace("_", " ").title(), value.replace("_", " ").title()]
        for name, value in risk_dimensions.items()
    ]
    risk_table = Table(risk_rows, colWidths=[3.45 * inch, 3.45 * inch])
    risk_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E3E7")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(risk_table)

    story.append(Paragraph("Model estimate", styles["Section"]))
    if prediction:
        story.append(
            Paragraph(
                "Calibrated synthetic severe-delinquency probability: <b>{:.1%}</b>. "
                "Risk band: <b>{}</b>. Confidence: <b>{}</b>.".format(
                    float(prediction.probability), prediction.risk_band, prediction.confidence
                ),
                normal,
            )
        )
        if prediction.uncertainty_reason:
            story.append(Paragraph("Uncertainty: " + prediction.uncertainty_reason, styles["Small"]))
    else:
        story.append(Paragraph("No model estimate was available; human review is required.", normal))

    story.extend(
        [
            PageBreak(),
            Paragraph("Decision, evidence, and reproducibility", styles["ReportTitle"]),
            Paragraph("Reasons and decision", styles["Section"]),
        ]
    )
    if reasons:
        for code in reasons:
            story.append(Paragraph("- " + code.replace("_", " ").title(), normal))
    else:
        story.append(Paragraph("No triggered reason codes.", normal))
    if decision:
        story.extend([Spacer(1, 6), Paragraph("<b>Decision summary:</b> " + decision.summary, normal)])
        conditions = _safe_json(decision.conditions_json, [])
        for condition in conditions:
            story.append(Paragraph("- Condition: " + condition, normal))

    story.extend(
        [
            Paragraph("Workflow record", styles["Section"]),
        ]
    )
    workflow_rows = [["Step", "Status", "Completed"]] + [
        [step.name.title(), step.status.replace("_", " ").title(), step.completed_at.isoformat() + "Z" if step.completed_at else "-"]
        for step in assessment.steps
    ]
    workflow = Table(workflow_rows, colWidths=[2.1 * inch, 1.7 * inch, 3.1 * inch], repeatRows=1)
    workflow.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), TEAL),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E3E7")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend(
        [
            workflow,
            Paragraph("Version record", styles["Section"]),
            Paragraph("Rule version: <b>{}</b><br/>Rule checksum: <font size=8>{}</font><br/>Model version: <b>{}</b>".format(assessment.rule_version, assessment.rule_checksum_sha256 or "-", assessment.model_version or "Unavailable"), normal),
            Paragraph("Limitations", styles["Section"]),
            Paragraph(
                "This report supports human review. The model was trained only on synthetic demonstration data and must not be used for lending, credit denial, sanctions confirmation, legal advice, or autonomous trade approval. Screening candidates require evidence-based human resolution. Reassess when transaction facts, counterparties, lists, rules, or model versions change.",
                normal,
            ),
        ]
    )
    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output.getvalue()
