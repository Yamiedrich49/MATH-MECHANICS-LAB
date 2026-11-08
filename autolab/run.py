#!/usr/bin/env python3
"""AUTOLAB: independent-role API calls, fail-closed evaluation, safe static publishing."""
from __future__ import annotations
import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
CONSTITUTION = (ROOT / "constitution.md").read_text(encoding="utf-8")
PRICES = {"gpt-6.1-sol": (2, 10), "gpt-6.1-terra": (1, 5), "gpt-6-luna": (.1, .5)}
def obj(props):
    return {"type":"object","properties":props,"required":list(props),"additionalProperties":False}
S = lambda typ: {"type":typ}
IDEAS = obj({"ideas":{"type":"array","items":obj({"title":S("string"),"hook":S("string"),"mechanic":S("string"),"turn_loop":S("string"),"aha":S("string"),"novelty":S("string")})}})
CRITIQUE = obj({"reviews":{"type":"array","items":obj({"title":S("string"),"score":S("integer"),"fatal":S("boolean"),"reason":S("string"),"fix":S("string")})}})
DESIGN = obj({"title":S("string"),"rules":S("string"),"first_ten_seconds":S("string"),"deep_strategy":S("string"),"prototype_scope":S("string"),"test_cases":{"type":"array","items":S("string")}})
VERDICT = obj({"score":S("integer"),"should_build":S("boolean"),"fatal_flaws":{"type":"array","items":S("string")},"changes":{"type":"array","items":S("string")}})
BUILD = obj({"html":S("string"),"notes":S("string")})
INSPECT = obj({"score":S("integer"),"fatal_flaws":{"type":"array","items":S("string")},"improvements":{"type":"array","items":S("string")}})

class BudgetError(RuntimeError):
    pass

class LabClient:
    def __init__(self, key, config):
        self.key, self.config, self.calls, self.tokens, self.cost = key, config, 0, 0, 0.0
        self.log = []
    def ask(self, role, model, schema, task, max_out=2400):
        if self.calls >= self.config["max_calls"] or self.tokens >= self.config["max_total_tokens"] or self.cost >= self.config["max_estimated_usd"]:
            raise BudgetError("Configured API call/token/estimated-cost ceiling reached")
        if not self.key:
            raise RuntimeError("OPENAI_API_KEY is required for live mode")
        instructions = ("You are an INDEPENDENT " + role + " in a game invention laboratory. "
                        "Do not flatter the user; challenge the idea. Output only valid JSON for the schema. "
                        "Your job is not to agree with any preceding agent.\n" + CONSTITUTION)
        payload = {"model":model,"instructions":instructions,"input":task,
                   "max_output_tokens":max_out,
                   "text":{"format":{"type":"json_schema","name":"lab_"+role.replace("-","_"),"strict":True,"schema":schema}}}
        req = urllib.request.Request("https://api.openai.com/v1/responses",
            data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
            headers={"Authorization":"Bearer "+self.key,"Content-Type":"application/json"},method="POST")
        # Count attempted calls, so retries do not silently multiply requests.
        self.calls += 1
        try:
            with urllib.request.urlopen(req,timeout=165) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as err:
            message = err.read(1500).decode("utf-8","replace")
            raise RuntimeError("OpenAI API HTTP "+str(err.code)+": "+message) from err
        if data.get("status") != "completed":
            raise RuntimeError("Model response not complete: "+str(data.get("status")))
        parts = [c.get("text","") for item in data.get("output",[])
                 if item.get("type") == "message"
                 for c in item.get("content",[]) if c.get("type") == "output_text"]
        if not parts:
            raise RuntimeError("Model returned no JSON output_text")
        usage = data.get("usage",{})
        inp, output = usage.get("input_tokens",0), usage.get("output_tokens",0)
        self.tokens += inp + output
        rate = PRICES.get(model, (3,15))
        self.cost += (inp*rate[0]+output*rate[1])/1_000_000
        self.log.append({"role":role,"model":model,"input_tokens":inp,"output_tokens":output})
        return json.loads("".join(parts))

class GameParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.errors=[]
        self.scripts=[]
        self.inscript=False
        self.has_viewport=False
        self.has_head=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="head": self.has_head=True
        if tag=="meta" and a.get("name","").lower()=="viewport": self.has_viewport=True
        if tag in ("iframe","object","embed","form","base","link"):
            self.errors.append("Forbidden HTML tag: "+tag)
        if tag=="script":
            if a.get("src") or a.get("type")=="module": self.errors.append("External/module scripts prohibited")
            self.inscript=True
            self.scripts.append("")
        for name,value in attrs:
            if name.startswith("on"): self.errors.append("Inline event attributes prohibited")
            if isinstance(value,str) and (value.startswith("http:") or value.startswith("https:") or value.startswith("//")):
                self.errors.append("External resource URL prohibited")
    def handle_endtag(self,tag):
        if tag=="script": self.inscript=False
    def handle_data(self,data):
        if self.inscript and self.scripts: self.scripts[-1]+=data

CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src 'none'; connect-src 'none'; media-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'"

def validate_html(source, maximum=58000):
    errors=[]
    if len(source)>maximum: errors.append("HTML over maximum size")
    p=GameParser()
    try: p.feed(source)
    except Exception as exc: errors.append("HTML parse: "+str(exc))
    errors+=p.errors
    if not p.has_head: errors.append("Missing head")
    if not p.has_viewport: errors.append("Missing responsive viewport")
    if len(p.scripts)!=1: errors.append("Exactly one inline script required")
    for token in ("fetch(", "XMLHttpRequest", "WebSocket(", "EventSource(", "navigator.sendBeacon",
                  "eval(", "new Function(", "document.cookie", "window.location=",
                  "import(", "@import", "url(http", "http://", "https://"):
        if token.lower() in source.lower(): errors.append("Prohibited network/dynamic behavior: "+token)
    if not errors and p.scripts:
        with tempfile.NamedTemporaryFile("w",suffix=".js",encoding="utf-8",delete=False) as tmp:
            tmp.write(p.scripts[0])
            js_path=Path(tmp.name)
        try:
            check=subprocess.run(["node","--check",str(js_path)],capture_output=True,text=True,timeout=15)
            if check.returncode: errors.append("JavaScript parse: "+check.stderr[-700:])
        except (FileNotFoundError,subprocess.TimeoutExpired):
            errors.append("Node JS syntax check unavailable")
        finally:
            js_path.unlink(missing_ok=True)
    return errors

def harden(source):
    meta='<meta http-equiv="Content-Security-Policy" content="'+html.escape(CSP,quote=True)+'">'
    return re.sub(r"(<head(?:\s[^>]*)?>)",lambda m:m.group(1)+"\n"+meta,source,count=1,flags=re.I)

def demo_game():
    return """<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>DEMO — SUM TO NINE</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#101822;color:#ecf0ed;font-family:-apple-system,system-ui,sans-serif;display:grid;min-height:100svh;place-items:center}main{width:min(92vw,420px);text-align:center}h1{font-size:12px;letter-spacing:4px;font-weight:600;color:#87a7a6}h2{font-size:27px;margin:10px 0 18px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}.cell{border:1px solid #3b505a;border-radius:16px;aspect-ratio:1;background:#1b2833;color:#f4f6ef;font-size:34px;touch-action:manipulation;transition:transform .1s,background .16s}.cell:active{transform:scale(.94)}.cell.on{background:#3e6660;border-color:#a1cfc0}p{color:#a5b8b5;font-size:14px;line-height:1.6}.mark{font-variant-numeric:tabular-nums;font-size:19px}button:focus-visible{outline:2px solid white;outline-offset:2px}</style></head><body><main><h1>RESEARCH DEMO</h1><h2>Make 9</h2><p>3つ選んで合計9。これはAIの発明ではなく動作確認専用です。</p><div class="grid" id="g"></div><p class="mark" id="s">0 / 9</p><p id="m">Tap three numbers</p></main><script>
const g=document.getElementById('g'),s=document.getElementById('s'),m=document.getElementById('m');let set=new Set();
[1,2,3,4,5,6,7,8,9].forEach(n=>{const b=document.createElement('button');b.className='cell';b.textContent=n;b.onclick=()=>{if(set.has(n)){set.delete(n);b.classList.remove('on')}else if(set.size<3){set.add(n);b.classList.add('on')}let sum=[...set].reduce((a,v)=>a+v,0);s.textContent=sum+' / 9';m.textContent=set.size===3?(sum===9?'✓ COMPLETE':'Try another combination'):'Tap three numbers';};g.appendChild(b)});
</script></body></html>"""

def run_research(client):
    prior=[]
    old=OUT/"latest.json"
    if old.exists():
        try: prior=json.loads(old.read_text(encoding="utf-8")).get("recent_titles",[])[:12]
        except (OSError,ValueError): pass
    log=[]
    idea=client.ask("inventor",CONFIG["idea_model"],IDEAS,
        "Propose SIX highly distinct, playable game cores across mathematics, physics, logic, spatial reasoning. "
        "Do not recycle existing games. Each hook must fit in one sentence. Already investigated names: "+json.dumps(prior,ensure_ascii=False),3800)
    concepts=idea.get("ideas",[])[:6]
    if len(concepts)<3: raise ValueError("Inventor produced too few ideas")
    critique=client.ask("skeptic",CONFIG["judge_model"],CRITIQUE,
        "Independently evaluate these ideas. Penalize superficial novelty, unthinking trial/error, tedious controls, and fake depth. "
        "Use scores 0-100, fatal true for hopeless concepts. Assess EACH EXACT title.\n"+json.dumps(concepts,ensure_ascii=False),3300)
    reviews={x["title"]:x for x in critique["reviews"]}
    candidates=sorted([(reviews.get(x["title"],{}).get("score",0),x) for x in concepts
                       if not reviews.get(x["title"],{}).get("fatal",True)],key=lambda z:z[0],reverse=True)
    if not candidates:
        return {"status":"REJECTED","reason":"All concepts vetoed","ideas":concepts,"reviews":critique["reviews"],"events":log},None
    selected=candidates[0][1]
    task="Turn this into a rules-complete, genuinely strategic puzzle with a 15-second onboarding; preserve one elegant core.\n"+json.dumps(selected,ensure_ascii=False)
    design=None; verdict=None
    for rnd in range(CONFIG["revision_rounds"]+1):
        design=client.ask("designer",CONFIG["idea_model"],DESIGN,task,3400)
        verdict=client.ask("adversarial_reviewer",CONFIG["judge_model"],VERDICT,
            "Criticize independently. Refuse unearned praise. Score 0-100, should_build only if a genuine, testable, original game and clear mobile control.\n"+json.dumps(design,ensure_ascii=False),1800)
        log.append({"round":rnd+1,"score":verdict["score"],"fatal_flaws":verdict["fatal_flaws"]})
        if verdict["score"]>=CONFIG["min_score"] and verdict["should_build"] and not verdict["fatal_flaws"]: break
        task="Redesign to address these problems without piling on gimmicks.\n"+json.dumps({"design":design,"review":verdict},ensure_ascii=False)
    base={"status":"REJECTED","title":selected["title"],"ideas":concepts,"reviews":critique["reviews"],
          "design":design,"verdict":verdict,"events":log,"reason":"Did not pass design gate"}
    if not (verdict["score"]>=CONFIG["min_score"] and verdict["should_build"] and not verdict["fatal_flaws"]):
        return base,None
    spec=("Build a COMPLETE, playable, visually restrained iPhone-portrait browser puzzle as ONE standalone HTML file. "
          "No remote assets, fetch, imports, frameworks, external fonts or scripts. ONE inline <script> only; CSS inline. "
          "Include viewport, touch interactions with large targets, undo/restart, concise onboarding, immediate success feedback, sound mute, localStorage progress if useful. "
          "Ensure at least five carefully constructed stages and solvable solutions. "
          "No placeholder buttons. Return valid document starting <!doctype html>. "
          "Have a precise objective and impossible-to-cheat success test.\n"+json.dumps(design,ensure_ascii=False))
    build=client.ask("implementer",CONFIG["build_model"],BUILD,spec,12500)
    candidate=build["html"].strip()
    errors=validate_html(candidate,CONFIG["max_html_chars"])
    if errors:
        base.update({"reason":"Prototype failed static safety/syntax gate","technical_issues":errors,"status":"REJECTED"})
        return base,None
    inspect=client.ask("independent_tester",CONFIG["judge_model"],INSPECT,
        "Find concrete logic bugs, ambiguous interactions, mathematical errors, and poor onboarding. "
        "Return fatal flaws even if prior designer was enthusiastic. Do NOT claim to have run a browser. "
        "Evaluate this code and design:\n"+json.dumps({"design":design,"html":candidate[:43000]},ensure_ascii=False),2300)
    if inspect["fatal_flaws"]:
        # One independent implementer repair; never bypass static validation.
        repaired=client.ask("repair_engineer",CONFIG["build_model"],BUILD,
            "Return complete corrected standalone HTML. Fix exactly these concrete concerns, no external assets.\n"+
            json.dumps({"html":candidate,"issues":inspect["fatal_flaws"]+inspect["improvements"]},ensure_ascii=False),12500)
        fresh=repaired["html"].strip()
        fresh_errors=validate_html(fresh,CONFIG["max_html_chars"])
        if fresh_errors:
            base.update({"reason":"Repair failed static safety/syntax gate","technical_issues":fresh_errors})
            return base,None
        candidate=fresh
        # We have not re-run a second independent AI audit: disclose this limitation.
        log.append({"note":"Repaired candidate passed static tests; independent re-review remains required"})
    base.update({"status":"CANDIDATE","reason":"AI-designed candidate; human playtest pending",
                 "title":design["title"],"implementation_notes":build["notes"],
                 "inspection":inspect,"technical_issues":[],"events":log})
    return base,harden(candidate)

def card_report(data,game_present):
    esc=lambda v:html.escape(str(v),quote=True)
    ideas=data.get("ideas",[])
    rows="".join("<div class='idea'><span>"+esc(i.get("title",""))+"</span><small>"+esc(i.get("hook",""))+"</small></div>" for i in ideas)
    gate=data.get("verdict",{})
    events=data.get("events",[])
    score=gate.get("score","—")
    frame=("<div class='preview'><iframe title='Prototype' src='./game.html' sandbox='allow-scripts'></iframe></div>" if game_present else "<p class='empty'>公開できる新作ゲームはありません。</p>")
    return """<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta http-equiv="Content-Security-Policy" content="default-src 'self'; frame-src 'self'; style-src 'unsafe-inline'; script-src 'none'; base-uri 'none'"><title>AUTOLAB / nightly research</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0e141a;color:#e9f0ee;font:15px/1.65 -apple-system,BlinkMacSystemFont,system-ui,sans-serif}.shell{width:min(900px,92vw);margin:0 auto;padding:38px 0 64px}header{display:flex;align-items:center;justify-content:space-between;gap:20px;border-bottom:1px solid #293941;padding-bottom:26px}h1{font-size:26px;letter-spacing:3px;font-weight:650;margin:0}h2{font-size:19px;font-weight:600;margin:0 0 14px}.sub,.hint,small{color:#94aaa9}.kicker{text-transform:uppercase;letter-spacing:2px;font-size:11px;color:#a7c9c0}section{padding:26px 0;border-bottom:1px solid #26353e}.stat{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.stat div{border:1px solid #32434b;border-radius:14px;padding:14px}.stat b{display:block;font-size:21px;font-weight:600;font-variant-numeric:tabular-nums}.stat span{font-size:11px;color:#91a6a5}.idea{padding:12px 0;border-bottom:1px solid #23323a}.idea span{display:block;font-weight:600}.idea small{display:block}.preview{margin-top:14px;border:1px solid #31444a;border-radius:24px;overflow:hidden;background:#101822;min-height:590px}.preview iframe{display:block;border:0;width:100%;height:640px}.empty{padding:40px;border:1px dashed #52656b;border-radius:18px;color:#b2c4c0}a{color:#a9dacf;text-decoration:none}.pill{font-size:11px;letter-spacing:1px;border:1px solid #5e7c72;border-radius:50px;padding:6px 10px;white-space:nowrap}.note{font-size:12px;color:#98adaa;line-height:1.8}@media(max-width:540px){header{align-items:flex-start}h1{font-size:21px}.stat{grid-template-columns:1fr 1fr}.stat div:last-child{grid-column:span 2}.preview iframe{height:650px}.shell{padding-top:24px}}</style></head><body><main class="shell">
<header><div><p class="kicker">AUTONOMOUS GAME RESEARCH</p><h1>AUTOLAB<span style="color:#86b4a9">.</span></h1><div class="sub">Nightly invention / critical review / prototype</div></div><span class="pill">__STATUS__</span></header>
<section><div class="stat"><div><b>__DATE__</b><span>研究実行日 JST</span></div><div><b>__SCORE__</b><span>内部設計審査（参考値）</span></div><div><b>__CALLS__</b><span>独立AI実行数</span></div></div></section>
<section><p class="kicker">TONIGHT'S RESULT</p><h2>__TITLE__</h2><p>__REASON__</p><p class="hint">AIの自己評価は人間のプレイ評価ではありません。動作・面白さ・数学的正確性は最終的に試遊で確認してください。</p></section>
<section><p class="kicker">PROTOTYPE</p><h2>Touch to play</h2>__FRAME__</section>
<section><p class="kicker">INVENTION SET</p><h2>探索した原理</h2>__IDEAS__</section>
<section><p class="kicker">RESEARCH LOG</p><p class="note">モデル消費トークン: __TOKENS__ / 推定API従量料金: $ __COST__（厳密な請求金額ではありません）</p><p class="note">__EVENTS__</p><p><a href="./latest.json">構造化研究ログを見る</a></p></section>
<footer class="note">AUTOLAB v1 · A critical research instrument, not a certification of game quality.</footer></main></body></html>""".replace("__STATUS__",esc(data["status"])).replace("__DATE__",esc(data["date"])).replace("__SCORE__",esc(score)).replace("__CALLS__",esc(data.get("api_calls",0))).replace("__TITLE__",esc(data.get("title","Research session"))).replace("__REASON__",esc(data.get("reason",""))).replace("__FRAME__",frame).replace("__IDEAS__",rows or "<p>No ideas yet.</p>").replace("__TOKENS__",esc(data.get("tokens",0))).replace("__COST__",esc(data.get("estimated_usd",0))).replace("__EVENTS__",esc(json.dumps(events,ensure_ascii=False)[:1200]))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--demo",action="store_true",help="No API calls, clearly labeled smoke test")
    ap.add_argument("--live",action="store_true")
    args=ap.parse_args()
    if args.demo==args.live: ap.error("Choose exactly one of --demo or --live")
    OUT.mkdir(parents=True,exist_ok=True)
    day=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d")
    if args.demo:
        data={"status":"DEMO","title":"Demo only: SUM TO NINE","reason":"No AI calls. Checks the pipeline and display; not a new invention.",
              "ideas":[{"title":"SUM TO NINE","hook":"Pick three tiles totaling nine. Simple UI smoke test only."}],
              "events":[{"stage":"demo","result":"No model calls made"}]}
        prototype=harden(demo_game())
        client=None
    else:
        client=LabClient(os.environ.get("OPENAI_API_KEY",""),CONFIG)
        if not client.key: raise RuntimeError("OPENAI_API_KEY missing: refused to run live mode")
        try: data,prototype=run_research(client)
        except (BudgetError,RuntimeError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
            data={"status":"ERROR","title":"Research interrupted","reason":str(exc)[:400],"events":[]}
            prototype=None
    data["date"]=day
    data["api_calls"]=client.calls if client else 0
    data["tokens"]=client.tokens if client else 0
    data["estimated_usd"]=round(client.cost,4) if client else 0
    data["models_used"]=client.log if client else []
    previous=[]
    old=OUT/"latest.json"
    if old.exists():
        try: previous=json.loads(old.read_text(encoding="utf-8")).get("recent_titles",[])
        except (OSError,ValueError): pass
    current=[x.get("title","") for x in data.get("ideas",[])]
    data["recent_titles"]=list(dict.fromkeys(current+previous))[:24]
    if prototype:
        if not args.demo:
            problems=validate_html(prototype,CONFIG["max_html_chars"]+1000)
            if problems:
                data["status"]="ERROR";data["reason"]="Post-hardening validation: "+str(problems);prototype=None
        if prototype:
            (OUT/"game.html").write_text(prototype,encoding="utf-8")
    (OUT/"latest.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    game_present=(OUT/"game.html").exists() and (prototype is not None)
    (OUT/"index.html").write_text(card_report(data,game_present),encoding="utf-8")
    (OUT/"report.md").write_text("# "+day+" / "+data["status"]+"\n\n"+data.get("title","")+"\n\n"+data.get("reason","")+"\n\nCalls: "+str(data["api_calls"])+" | Estimated USD: "+str(data["estimated_usd"])+"\n",encoding="utf-8")
    if data["status"]=="ERROR": raise RuntimeError("Research failed: "+data.get("reason",""))
    print(json.dumps({"date":day,"status":data["status"],"calls":data["api_calls"],"usd":data["estimated_usd"]},ensure_ascii=False))

if __name__=="__main__":
    main()
