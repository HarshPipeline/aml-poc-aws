"""Build synthetic case-file PDFs and the Casa Brisa check PNG. Not used at runtime.

Run from the repo root:
    .venv/bin/python aml_poc/fixtures/evidence/build_pdfs.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
NAVY = colors.HexColor("#1B2A4A")
GOLD = colors.HexColor("#B8860B")
RULE = colors.HexColor("#C5CBD3")
ROW = colors.HexColor("#F4F1EA")
INK = colors.HexColor("#1A1A1A")
MUTED = colors.HexColor("#5C6570")
BANNER = "SYNTHETIC DEMONSTRATION RECORD — NOT A REAL BANK, INVOICE, OR NEGOTIABLE INSTRUMENT"


def styles():
    base = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle(
            "kicker", parent=base["Normal"], fontName="Times-Bold", fontSize=8,
            textColor=GOLD, letterSpacing=1.2, spaceAfter=2,
        ),
        "title": ParagraphStyle(
            "title", parent=base["Normal"], fontName="Times-Bold", fontSize=18,
            textColor=NAVY, spaceAfter=2, leading=22,
        ),
        "entity": ParagraphStyle(
            "entity", parent=base["Normal"], fontName="Times-Bold", fontSize=13,
            textColor=NAVY, leading=16,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontName="Times-Roman", fontSize=10,
            textColor=INK, leading=14, alignment=TA_JUSTIFY,
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"], fontName="Times-Roman", fontSize=8.5,
            textColor=MUTED, leading=12,
        ),
        "label": ParagraphStyle(
            "label", parent=base["Normal"], fontName="Times-Bold", fontSize=8,
            textColor=MUTED, leading=11,
        ),
        "value": ParagraphStyle(
            "value", parent=base["Normal"], fontName="Times-Roman", fontSize=10,
            textColor=INK, leading=13,
        ),
        "right": ParagraphStyle(
            "right", parent=base["Normal"], fontName="Times-Roman", fontSize=10,
            textColor=INK, alignment=TA_RIGHT, leading=13,
        ),
        "rightBold": ParagraphStyle(
            "rightBold", parent=base["Normal"], fontName="Times-Bold", fontSize=10,
            textColor=INK, alignment=TA_RIGHT, leading=13,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"], fontName="Times-Italic", fontSize=8,
            textColor=MUTED, alignment=TA_CENTER, leading=11,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["Normal"], fontName="Times-Roman", fontSize=9,
            textColor=INK, leading=12,
        ),
        "cellBold": ParagraphStyle(
            "cellBold", parent=base["Normal"], fontName="Times-Bold", fontSize=9,
            textColor=INK, leading=12,
        ),
        "head": ParagraphStyle(
            "head", parent=base["Normal"], fontName="Times-Bold", fontSize=8,
            textColor=colors.white, leading=11,
        ),
    }


def watermark(c: canvas.Canvas, text="SYNTHETIC"):
    c.saveState()
    c.setFillColor(colors.Color(0.82, 0.78, 0.70, alpha=0.28))
    c.setFont("Times-Bold", 64)
    c.translate(320, 400)
    c.rotate(38)
    c.drawCentredString(0, 0, text)
    c.restoreState()


def page_chrome(c: canvas.Canvas, doc):
    watermark(c)
    c.setFillColor(NAVY)
    c.rect(0, letter[1] - 18, letter[0], 18, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Times-Bold", 8)
    c.drawString(0.7 * inch, letter[1] - 13, "CASE FILE  ·  BSA / AML EVIDENCE  ·  FOR INVESTIGATOR REVIEW")
    c.setFont("Times-Roman", 8)
    c.drawRightString(letter[0] - 0.7 * inch, letter[1] - 13, "DEMO ONLY")
    c.setFillColor(GOLD)
    c.rect(0, letter[1] - 22, letter[0], 4, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.rect(0, 0, letter[0], 28, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Times-Roman", 7)
    c.drawCentredString(letter[0] / 2, 12, BANNER)


def money(n):
    return f"${n:,.2f}"


def invoice(path, *, issuer, issuer_addr, bill_to, bill_addr, number, date, due, po, lines, total, notes, payment):
    s = styles()
    doc = SimpleDocTemplate(
        str(path), pagesize=letter,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.55 * inch, bottomMargin=0.55 * inch,
    )
    story = [
        Paragraph("COMMERCIAL INVOICE", s["kicker"]),
        Paragraph(issuer, s["title"]),
        Paragraph("<br/>".join(issuer_addr), s["small"]),
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceAfter=12),
    ]
    meta = Table(
        [
            [
                Paragraph("BILL TO", s["label"]),
                Paragraph("INVOICE", s["label"]),
            ],
            [
                Paragraph(f"<b>{bill_to}</b><br/>{'<br/>'.join(bill_addr)}", s["value"]),
                Paragraph(
                    f"No. <b>{number}</b><br/>Date: {date}<br/>Due: {due}<br/>Ref: {po}",
                    s["right"],
                ),
            ],
        ],
        colWidths=[4.2 * inch, 2.9 * inch],
    )
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [meta, Spacer(1, 16)]
    header = [Paragraph(h, s["head"]) for h in ["Description", "Qty", "Unit price", "Amount"]]
    rows = [header]
    for desc, qty, unit, amt in lines:
        rows.append([
            Paragraph(desc, s["cell"]),
            Paragraph(str(qty), s["cell"]),
            Paragraph(money(unit), s["cell"]),
            Paragraph(money(amt), s["cellBold"]),
        ])
    rows.append([
        "", "", Paragraph("TOTAL DUE (USD)", s["cellBold"]),
        Paragraph(money(total), s["cellBold"]),
    ])
    table = Table(rows, colWidths=[3.8 * inch, 0.8 * inch, 1.25 * inch, 1.25 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), ROW),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -2), 0.3, RULE),
        ("BOX", (0, 0), (-1, -1), 0.6, NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 1), (-1, -2), colors.white),
        *[("BACKGROUND", (0, i), (-1, i), ROW) for i in range(1, len(rows) - 1) if i % 2 == 0],
    ]))
    story += [
        table, Spacer(1, 14),
        Paragraph("PAYMENT INSTRUCTIONS", s["label"]),
        Paragraph(payment, s["body"]),
        Spacer(1, 8),
        Paragraph("NOTES", s["label"]),
        Paragraph(notes, s["small"]),
        Spacer(1, 16),
        Paragraph(
            "This document is a fictional exhibit for an AML investigation demonstration. "
            "Names, addresses, goods, and amounts are synthetic and must not be treated as a live commercial claim.",
            s["footer"],
        ),
    ]
    doc.build(story, onFirstPage=page_chrome, onLaterPages=page_chrome)


def letter_pdf(path, *, from_block, to_block, date, subject, body, sign):
    s = styles()
    doc = SimpleDocTemplate(
        str(path), pagesize=letter,
        leftMargin=0.85 * inch, rightMargin=0.85 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
    )
    story = [
        Paragraph("CUSTOMER CORRESPONDENCE  ·  INFORMATION RESPONSE", s["kicker"]),
        Paragraph(from_block[0], s["title"]),
        Paragraph("<br/>".join(from_block[1:]), s["small"]),
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceAfter=12),
        Paragraph(date, s["small"]),
        Spacer(1, 8),
        Paragraph("TO", s["label"]),
        Paragraph("<br/>".join(to_block), s["value"]),
        Spacer(1, 10),
        Paragraph(f"Re: <b>{subject}</b>", s["body"]),
        Spacer(1, 10),
    ]
    for para in body:
        story += [Paragraph(para, s["body"]), Spacer(1, 8)]
    story += [
        Spacer(1, 6),
        Paragraph("Respectfully,", s["body"]),
        Spacer(1, 18),
        HRFlowable(width=2.4 * inch, thickness=0.6, color=INK),
        Paragraph(sign, s["value"]),
        Spacer(1, 18),
        Paragraph(
            "Synthetic demonstration correspondence. Not a customer statement from a live financial institution.",
            s["footer"],
        ),
    ]
    doc.build(story, onFirstPage=page_chrome, onLaterPages=page_chrome)


def _font(size, bold=False):
    names = (
        ("Times New Roman Bold.ttf", "Times New Roman.ttf")
        if bold
        else ("Times New Roman.ttf",)
    )
    roots = (
        Path("/System/Library/Fonts/Supplemental"),
        Path("/Library/Fonts"),
        Path("/usr/share/fonts/truetype/liberation"),
    )
    for root in roots:
        for name in names:
            path = root / name
            if path.exists():
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def check_png(path, *, payer, payer_addr, number, date, payee, amount, words, memo, txn, sign):
    w, h = 1800, 760
    img = Image.new("RGB", (w, h), "#F7F4EE")
    d = ImageDraw.Draw(img)
    navy, gold, ink, muted = "#1B2A4A", "#B8860B", "#1A1A1A", "#5C6570"
    d.rectangle([0, 0, w - 1, h - 1], outline=navy, width=8)
    d.rectangle([8, 8, w - 9, 52], fill=navy)
    d.text((28, 18), "CASE FILE  ·  CHECK IMAGE  ·  DEMO ONLY", font=_font(22, True), fill="white")
    d.text((w - 28, 18), "SYNTHETIC", font=_font(22, True), fill="#E8C56B", anchor="ra")
    d.rectangle([8, 52, w - 9, 60], fill=gold)
    d.text((40, 88), payer, font=_font(34, True), fill=navy)
    d.text((40, 132), payer_addr, font=_font(18), fill=muted)
    d.text((w - 40, 88), f"CHECK NO.  {number}", font=_font(24, True), fill=navy, anchor="ra")
    d.text((w - 40, 128), date, font=_font(20), fill=ink, anchor="ra")
    d.line([40, 170, w - 40, 170], fill=gold, width=4)
    d.text((40, 198), "PAY TO THE ORDER OF", font=_font(16, True), fill=muted)
    d.text((40, 232), payee, font=_font(30, True), fill=ink)
    d.line([40, 278, w - 320, 278], fill=navy, width=2)
    d.rectangle([w - 300, 210, w - 40, 278], outline=navy, width=2)
    d.text((w - 52, 228), money(amount), font=_font(28, True), fill=ink, anchor="ra")
    d.text((40, 310), words, font=_font(22), fill=ink)
    d.line([40, 348, w - 40, 348], fill=navy, width=1)
    d.text((40, 390), "MEMO", font=_font(16, True), fill=muted)
    d.text((120, 388), memo, font=_font(20), fill=ink)
    d.line([120, 418, 780, 418], fill=navy, width=1)
    d.text((920, 390), "AUTHORIZED SIGNATURE", font=_font(16, True), fill=muted)
    d.text((920, 428), sign, font=_font(26), fill=ink)
    d.line([920, 468, w - 40, 468], fill=navy, width=1)
    d.rectangle([8, 640, w - 9, h - 9], fill="#EEF2F7")
    d.text((40, 668), f"A000000000A  0000000000C  {number}", font=_font(22, True), fill=navy)
    d.text((w - 40, 668), f"Demo Bank · fictional routing · {txn}", font=_font(16), fill=muted, anchor="ra")
    d.text((w // 2, 500), "SYNTHETIC", font=_font(72, True), fill="#E4D9C4", anchor="mm")
    d.text(
        (w // 2, 580),
        "Not a negotiable instrument. For AML demonstration / Textract OCR only.",
        font=_font(16),
        fill=muted,
        anchor="mm",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")


def build():
    c001 = ROOT / "C001"
    c002 = ROOT / "C002"
    c003 = ROOT / "C003"
    c004 = ROOT / "C004"
    for folder in (c001, c002, c003, c004):
        folder.mkdir(parents=True, exist_ok=True)

    store = "Sunnyvale Corner Quick Stop LLC"
    owner = "Marcus Delgado-Whitfield"
    letter_pdf(
        c001 / "SOF-marcus-delgado-whitfield.pdf",
        from_block=[store, "SYNTH 100 Example St, Sunnyvale, CA 94000", owner, "Managing Member"],
        to_block=[
            "Financial Crimes Investigations",
            "Demo Bank — BSA / AML Operations",
            "Case reference: customer C001  ·  account ACC-C001-01",
        ],
        date="22 October 2025",
        subject="Source of funds for cash deposits 14–20 October 2025",
        body=[
            "I am writing in response to the review of five cash deposits totaling "
            "$46,492.00 posted to ACC-C001-01 between 14 and 20 October 2025 (TXN-000090, TXN-000097, "
            "TXN-000133, TXN-000145, TXN-000171). Each deposit was made in person by me at branch SYNTH-BR-CA-001.",
            "The funds are register receipts from Sunnyvale Corner Quick Stop LLC. Card sales settle separately "
            "and are not mixed into these deposits. I am the sole depositor and beneficial owner.",
            "That week was heavier than our usual $600–$1,800 cash drop because of a nearby campus event and "
            "elevated lottery-ticket cash. I did not structure the deposits to avoid a currency transaction report.",
            "Please treat this letter as the source-of-funds explanation requested for the flagged cash activity. "
            "This is a synthetic demonstration response.",
        ],
        sign=f"{owner}<br/>Managing Member<br/>{store}",
    )

    importer = "Pacific Rim Circuitry Imports Inc."
    importer_addr = ["SYNTH 400 Example Blvd", "Fremont, CA 94500", "EIN SYNTH-XX-XXX0004"]
    invoice(
        c004 / "INV-GYEONGGI-PRC-60000.pdf",
        issuer="Gyeonggi Display Systems Ltd.",
        issuer_addr=["SYNTH 88 Pangyo-ro", "Seongnam, Gyeonggi, Republic of Korea", "Export desk: docs@gyeonggi.example"],
        bill_to=importer,
        bill_addr=importer_addr,
        number="GDS-INV-2025-4410",
        date="01 Nov 2025",
        due="10 Nov 2025",
        po="PRC-PO-4410",
        lines=[
            ("15.6-inch TFT display panels, commercial grade", 500, 98.00, 49000.00),
            ("Display driver IC, reel", 2000, 4.50, 9000.00),
            ("Export packing and inland freight to Busan", 1, 1000.00, 1000.00),
        ],
        total=60000.00,
        notes="Payment by international wire 10 Nov 2025. Demo ledger TXN-000437. Wire message left invoice/purpose blank; this invoice is the commercial support.",
        payment="Beneficiary: Gyeonggi Display Systems Ltd. Amount USD 60,000.00 even. Incoterms FOB Busan (demo).",
    )
    invoice(
        c004 / "INV-HSINCHU-PRC-55000.pdf",
        issuer="Hsinchu Microlink Electronics Co.",
        issuer_addr=["SYNTH 12 Science Park Rd", "Hsinchu, Taiwan", "Export desk: ar@microlink.example"],
        bill_to=importer,
        bill_addr=importer_addr,
        number="HME-INV-2025-2288",
        date="05 Nov 2025",
        due="14 Nov 2025",
        po="PRC-PO-2288",
        lines=[
            ("RF transceiver modules, 2.4 GHz", 250, 180.00, 45000.00),
            ("Board-level connectors, tape-and-reel", 5000, 1.60, 8000.00),
            ("Air freight prepaid", 1, 2000.00, 2000.00),
        ],
        total=55000.00,
        notes="Paid by international wire 14 Nov 2025. Demo ledger TXN-000485. Counterparty CP-C004-002.",
        payment="Wire USD 55,000.00. Contract price is a round amount per framework agreement PRC-FA-2024.",
    )
    invoice(
        c004 / "INV-SHENZHEN-PRC-80000.pdf",
        issuer="Shenzhen Brightway Components Co. Ltd.",
        issuer_addr=["SYNTH 19 Huaqiang North", "Shenzhen, Guangdong, China", "Export desk: finance@brightway.example"],
        bill_to=importer,
        bill_addr=importer_addr,
        number="SBW-INV-2025-9014",
        date="08 Nov 2025",
        due="18 Nov 2025",
        po="PRC-PO-9014",
        lines=[
            ("N-channel power MOSFET, 60V, reel", 10000, 5.20, 52000.00),
            ("Populated PCB assemblies, power stage", 80, 300.00, 24000.00),
            ("Cargo insurance and ocean freight", 1, 4000.00, 4000.00),
        ],
        total=80000.00,
        notes="Paid by international wire 18 Nov 2025. Demo ledger TXN-000535. Counterparty CP-C004-001.",
        payment="Beneficiary Shenzhen Brightway Components Co. Ltd. Amount USD 80,000.00.",
    )
    letter_pdf(
        c004 / "LTR-third-party-crescent-meridian.pdf",
        from_block=[importer, "SYNTH 400 Example Blvd, Fremont, CA 94500", "Wei-Lin Tran-Castellano", "President"],
        to_block=[
            "Financial Crimes Investigations",
            "Demo Bank — BSA / AML Operations",
            "Case reference: customer C004  ·  account ACC-C004-01",
        ],
        date="21 November 2025",
        subject="Purpose of payment and third-party payer — incoming wire TXN-004827 ($365,000.00)",
        body=[
            "On 4 November 2025 we received an international wire of USD 365,000.00 from Crescent Meridian "
            "General Trading FZE, United Arab Emirates (TXN-004827). The wire message did not carry a purpose "
            "or invoice reference. This letter and the enclosed supplier invoices are our response.",
            "Crescent Meridian is not a manufacturer. They told us they act as a regional buying agent for a "
            "Gulf distributor that purchases our U.S. inventory. They asked to prepay three Asian supplier "
            "invoices that we would then settle by wire: GDS-INV-2025-4410 ($60,000), HME-INV-2025-2288 "
            "($55,000), and SBW-INV-2025-9014 ($80,000), with the remainder applied to future purchase orders.",
            "We do not have a long-standing contract with Crescent Meridian. AE is outside our expected "
            "operating countries (US, CN, TW, KR, HK). We are providing this explanation and the invoices "
            "so the investigator can assess the relationship. This letter does not certify that the activity "
            "is legitimate.",
            "A later incoming wire from Lionsgate Harbor Holdings Pte. Ltd. (SG), TXN-004835 for $340,000.00 "
            "on 19 November 2025, was described to us as a similar agency prepayment. We have not attached "
            "a separate contract for that payer.",
        ],
        sign="Wei-Lin Tran-Castellano<br/>President<br/>Pacific Rim Circuitry Imports Inc.",
    )

    check_png(
        c002 / "CHK-3957-delta-fresh.png",
        payer="Casa Brisa Kitchen Inc.",
        payer_addr="SYNTH 200 Example Ave, San Jose, CA 95000  ·  ACC-C002-01",
        number="3957",
        date="19 Nov 2025",
        payee="Delta Fresh Produce Co.",
        amount=6892.36,
        words="Six thousand eight hundred ninety-two and 36/100 dollars",
        memo="TXN-000559  ·  no invoice on check",
        txn="TXN-000559",
        sign="E. Quintanilla-Hayes",
    )
    invoice(
        c003 / "INV-KESTREL-HP-4419.pdf",
        issuer="Kestrel Health Partners",
        issuer_addr=["SYNTH 77 Medical Plaza", "Palo Alto, CA 94300", "AP: billing@kestrel.example"],
        bill_to="Priya Anand-Sorensen",
        bill_addr=["Freelance consultant", "SYNTH 300 Example Ln", "Palo Alto, CA 94300"],
        number="HP-4419",
        date="15 Dec 2025",
        due="16 Dec 2025",
        po="Verbal / same-day remit",
        lines=[
            ("Implementation support — week of 15 Dec 2025", 1, 5800.00, 5800.00),
            ("Rush processing", 1, 355.33, 355.33),
        ],
        total=6155.33,
        notes=(
            "Pay by wire 16 Dec 2025. Demo ledger TXN-000917. Amount is within 0.5% of the Northbeam "
            "incoming wire TXN-000889 ($6,183.48) posted the previous day. KYC lists Kestrel as a client "
            "(expected incoming); this invoice bills Priya instead. Weak / incomplete support for pass-through review."
        ),
        payment="Wire USD 6,155.33 to Kestrel Health Partners. No contract attached.",
    )
    print("Wrote evidence files under", ROOT)


if __name__ == "__main__":
    build()

