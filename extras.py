import os
import io,re,json,urllib.request
from ai_provider import generate_ai
from xml.sax.saxutils import escape
from flask import request,jsonify,send_file

def register(app,data,system,context_prompt):
    app.config['MAX_CONTENT_LENGTH']=8*1024*1024
    @app.post('/bill')
    def bill():
        import fitz
        f=request.files.get('bill')
        if not f: return jsonify(error='Choose a PDF first.'),400
        try:
            with fitz.open(stream=f.read(),filetype='pdf') as doc:
                if doc.is_encrypted: raise ValueError('Encrypted PDF')
                text='\n'.join(p.get_text() for p in list(doc)[:10])[:24000]
            if not text.strip(): return jsonify(error='No selectable text found. Scanned bills require OCR, not included.'),400
            patterns={'Consumption (kWh)':r'(?:units consumed|consumption|energy consumed|billed units)\s*[:=]?\s*([\d,.]+)', 'Amount due (INR)':r'(?:total amount due|amount payable|net payable|amount due|total bill amount)\s*[:=]?\s*(?:₹|Rs\.?|INR)?\s*([\d,.]+)', 'Billing period':r'(?:billing period|bill period)\s*[:=]?\s*([^\n]{3,80})'}
            fields={k:(m.group(1) if (m:=re.search(v,text,re.I)) else 'Not detected') for k,v in patterns.items()}
            return jsonify(fields=fields,note='Candidate fields only; verify against original bill. First 10 pages processed by the application server. No upload retained.')
        except Exception: return jsonify(error='Could not read this PDF. Use an unlocked, valid text PDF.'),400
    @app.get('/report')
    def report():
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        d=data(); b=io.BytesIO(); s=getSampleStyleSheet(); story=[Paragraph('EnergySense AI | Energy report',s['Title']),Paragraph('Sample data' if d['settings']['demo'] else 'User-entered data',s['Normal']),Spacer(1,14),Paragraph(f"Monthly estimate: {d['total']} kWh | INR {d['bill']} | Carbon: {d['carbon']} kg CO2",s['Heading2']),Paragraph(f"Tariff: INR {d['settings']['rate']}/kWh. Forecast: {d['forecast']} kWh (recent average).",s['Normal']),Spacer(1,12)]
        rows=[['Appliance','kWh','Cost (INR)','Potential saving (INR)']]+[[Paragraph(escape(a['name']),s['Normal']),str(a['units']),str(a['cost']),str(a['saving'])] for a in d['appliances']]
        t=Table(rows,colWidths=[165,65,90,145],repeatRows=1);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#123b46')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.whitesmoke,colors.white]),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),9)]));story.extend([t,Spacer(1,15),Paragraph('Estimates assume 30 days and exclude fixed charges and taxes. Savings assume up to one hour less daily use when safe and practical. Carbon uses the configured illustrative factor.',s['Normal'])]);SimpleDocTemplate(b,pagesize=A4).build(story);b.seek(0);return send_file(b,mimetype='application/pdf',as_attachment=True,download_name='EnergySense_report.pdf')
    @app.post('/playground')
    def playground():

        q = str(
            (request.get_json(silent=True) or {})
            .get('question', '')
        ).strip()[:500]

        if (
            not q
            or not re.search(
                r'electric|energy|bill|appliance|kwh|saving|consumption|bijli|tariff|\bac\b',
                q, re.I
            )
            or re.search(r'wir|bypass|tamper|hack', q, re.I)
        ):
            return jsonify(
                error="Use a safe household energy question."
            ), 400

        d = data()
        engineered = context_prompt(d, q)

        if os.getenv("AI_PROVIDER", "ollama") == "demo":

            basic = (
                "[Illustrative demo - not AI-generated]\n\n"
                "Reduce unnecessary appliance usage, "
                "switch off unused lights and fans, "
                "and use energy-efficient appliances."
            )

            contextual = (
                "[Illustrative demo - not AI-generated]\n\n"
                f"Monthly consumption: {d['total']} kWh.\n"
                f"Estimated bill: INR {d['bill']}.\n"
                f"Tariff: INR {d['settings']['rate']}/kWh.\n"
            )

            top = d['top']

            if top:
                contextual += (
                    f"Highest consuming appliance: "
                    f"{top['name']}.\n"
                    f"Monthly consumption: "
                    f"{top['units']} kWh.\n"
                    f"Potential monthly saving: "
                    f"INR {top['saving']} by reducing "
                    "daily usage by up to one hour, "
                    "when safe and practical."
                )

            return jsonify(
                basic=basic,
                engineered=contextual,
                prompt=engineered,
                system=system,
                mode="Illustrative Demo"
            )

        try:
            basic, _ = generate_ai(
                "Answer household energy questions briefly "
                "and safely. Do not invent facts.",
                q
            )

            improved, _ = generate_ai(
                system, engineered
            )

            return jsonify(
                basic=basic,
                engineered=improved,
                prompt=engineered,
                system=system,
                mode="Ollama Generative AI"
            )

        except Exception:
            return jsonify(
                error="Ollama unavailable or timed out."
            ), 503
