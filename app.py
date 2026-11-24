import os, math, re
from flask import Flask,render_template,request,redirect,url_for,jsonify,abort,session
from dotenv import load_dotenv
from database import connect,init,seed
from prompts import SYSTEM,context_prompt
load_dotenv(); app=Flask(__name__); app.secret_key=os.urandom(32); init()
def number(key,lo,hi):
    v=float(request.form[key]);
    if not math.isfinite(v) or not lo<=v<=hi: raise ValueError(key)
    return v
def data():
    with connect() as c:
        s=dict(c.execute('SELECT * FROM settings').fetchone()); a=[dict(r) for r in c.execute('SELECT * FROM appliances ORDER BY id')]; h=[dict(r) for r in c.execute('SELECT * FROM history ORDER BY month')]
    for x in a:
        x['units']=round(x['watts']*x['qty']*x['hours']*30/1000,2); x['cost']=round(x['units']*s['rate'],2); x['saving']=round(x['watts']*x['qty']*min(1,x['hours'])*30/1000*s['rate'],2)
    total=round(sum(x['units'] for x in a),2); forecast=round(sum(x['units'] for x in h[-3:])/len(h[-3:]),2) if h else None
    return dict(appliances=a,history=h,settings=s,total=total,bill=round(total*s['rate'],2),carbon=round(total*s['factor'],2),forecast=forecast,top=max(a,key=lambda x:x['units']) if a else None)
@app.route('/')
def index(): return render_template('index.html',d=data())
@app.post('/change')
def change():
    try:
        action=request.form['action']
        with connect() as c:
            if action in ('add','edit'):
                name=request.form['name'].strip(); qty=number('qty',1,1000)
                if not name or len(name)>100 or qty!=int(qty): raise ValueError('name or quantity')
                vals=(name,number('watts',0,100000),int(qty),number('hours',0,24))
                if action=='add': c.execute('INSERT INTO appliances(name,watts,qty,hours) VALUES(?,?,?,?)',vals)
                else: c.execute('UPDATE appliances SET name=?,watts=?,qty=?,hours=? WHERE id=?',vals+(int(request.form['id']),))
            elif action=='delete': c.execute('DELETE FROM appliances WHERE id=?',(int(request.form['id']),))
            elif action=='history':
                m=request.form['month'];
                if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',m): raise ValueError('month')
                c.execute('INSERT OR REPLACE INTO history VALUES(?,?)',(m,number('units',0,1000000)))
            elif action=='remove_history': c.execute('DELETE FROM history WHERE month=?',(request.form['month'],))
            elif action=='settings': c.execute('UPDATE settings SET rate=?,factor=?',(number('rate',0,1000),number('factor',0,10)))
            elif action in ('reset','clear'):
                c.execute('DELETE FROM appliances'); c.execute('DELETE FROM history'); c.execute('UPDATE settings SET demo=?',(int(action=='reset'),));
                if action=='reset': seed(c)
            else: abort(400)
    except (ValueError,KeyError,OverflowError): return 'Invalid input. Go back and check the values.',400
    return redirect(url_for('index')+'#'+request.form.get('section','dashboard'))
@app.post('/chat')
def chat():
    q=str((request.get_json(silent=True) or {}).get('question','')).strip()[:1500]
    if not q: return jsonify(answer='Enter a question.',mode='Error'),400
    d=data(); top=d['top']; fallback=(f"Monthly estimate: {d['total']} kWh, ₹{d['bill']}. " + (f"Highest consuming appliance: {top['name']} ({top['units']} kWh). Reducing its daily usage by up to one hour, when practical, could save ₹{top['saving']} per month." if top else 'Add appliances to get insights.')+' Estimates exclude fixed charges and taxes.')
    # Conservative domain gate: no model call for unrelated questions.
    if not re.search(r"electric|energy|power|kwh|watt|tariff|appliance|bill|consumption|carbon|forecast|saving|\bac\b|fan|fridge|refrigerator|solar|bijli|बिजली|ऊर्जा|बिल|unit|मीटर|meter|television|\btv\b", q, re.I):
        return jsonify(answer="I can only help with household electricity, bills, appliances and energy savings. Please ask an energy-related question.", mode="Domain guardrail")
    if re.search(r"rewir|bypass|tamper|live wire|meter hack|wiring", q, re.I):
        return jsonify(answer="For electrical wiring or meter issues, contact a qualified electrician or your electricity provider.", mode="Safety guardrail")
    hinglish = bool(re.search(r"hinglish|\bmera\b|\bmujhe\b|\bkaise\b|\bbatao\b", q, re.I))
    if top and re.search(r"highest|most electricity|sabse zyada|top appliance", q, re.I) and not re.search(r"plan|recommend|suggest|reduce", q, re.I):
        answer = (f"Sabse zyada electricity {top['name']} consume karta hai: {top['units']} kWh per month." if hinglish else f"{top['name']} has the highest estimated monthly consumption: {top['units']} kWh.")
        return jsonify(answer=answer, mode="Verified calculation")
    if re.search(r"one hour|1 hour|1 ghanta|ek ghanta", q, re.I) and re.search(r"sav|reduc|kam|bach", q, re.I):
        matches = [a for a in d['appliances'] if a['name'].lower() in q.lower() or (re.search(r"\bac\b", q, re.I) and 'air conditioner' in a['name'].lower())]
        if len(matches)==1:
            a=matches[0]; units=round(a['watts']*a['qty']*min(1,a['hours'])*30/1000,2)
            answer=f"{a['name']}: estimated monthly saving is {units} kWh and ₹{a['saving']} at ₹{d['settings']['rate']}/kWh, assuming up to one hour less usage daily for 30 days."
            if hinglish: answer=f"{a['name']} ka daily usage ek ghanta tak kam karne se 30 din mein {units} units aur ₹{a['saving']} ki estimated saving hogi."
            return jsonify(answer=answer, mode="Verified calculation")
    try:
        import json, urllib.request
        prompt = context_prompt(d, q)
        if hinglish: prompt += "\nAnswer in Roman-script Hinglish only."
        payload = {'model':'qwen2.5:3b','messages':[{'role':'system','content':SYSTEM},{'role':'user','content':prompt}], 'stream':False,'options':{'temperature':0.15,'num_predict':220,'repeat_penalty':1.2,'repeat_last_n':128}}
        req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(payload).encode('utf-8'),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=180) as response:
            answer=json.load(response)['message']['content'].strip()
        words=answer.lower().split()
        grams=[tuple(words[i:i+4]) for i in range(len(words)-3)]
        if not answer or (grams and len(set(grams))/len(grams)<0.65) or (hinglish and re.search(r"[\u0900-\u097f]",answer)):
            raise ValueError('Response quality check failed')
        return jsonify(answer=answer,mode='Ollama AI - Qwen2.5')
    except Exception as e:
        print('Ollama error:',e)
        if hinglish:
            fallback=f"Monthly estimate {d['total']} units aur ₹{d['bill']} hai. " + (f"{top['name']} ka usage practical hone par ek ghanta tak kam karne se ₹{top['saving']} monthly save ho sakte hain." if top else "Pehle appliances add karein.")
        return jsonify(answer=fallback,mode='Rule-based fallback - AI unavailable or quality check failed')
from extras import register
register(app,data,SYSTEM,context_prompt)
if __name__=='__main__': app.run(host='127.0.0.1',port=5000,debug=False)
