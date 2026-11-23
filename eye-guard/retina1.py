import time, threading, collections
import cv2, numpy as np, mediapipe as mp
from flask import Flask, jsonify, render_template_string

# ---------- SETTINGS ----------
WORK_LIMIT_SEC   = 3 * 3600   # warn after 3 hours (use 60 to test quickly)
AWAY_RESET_SEC   = 5 * 60     # no face for 5 min = you took a break, reset timer
LOW_BLINK_PER_MIN = 8         # normal is ~15-20
REDNESS_INCREASE = 0.12       # warn if redness is 12% above your baseline
CALIBRATION_SEC  = 60         # first minute = your "normal" eye colour
# ------------------------------

LEFT  = [33, 160, 158, 133, 153, 144]
RIGHT = [362, 385, 387, 263, 373, 380]

state = dict(work_sec=0, face=False, blinks_per_min=None,
             redness=None, baseline=None, warnings=[], calibrating=True, error=None)
lock = threading.Lock()
stop_event = threading.Event()

def reset():
    stop_event.clear()
    with lock:
        state.update(work_sec=0, face=False, blinks_per_min=None, redness=None,
                     baseline=None, warnings=[], calibrating=True, error=None)

def ear(pts):
    a = np.linalg.norm(pts[1] - pts[5]); b = np.linalg.norm(pts[2] - pts[4])
    c = np.linalg.norm(pts[0] - pts[3])
    return (a + b) / (2.0 * c)

def eye_redness(frame, pts):
    mask = np.zeros(frame.shape[:2], np.uint8)
    cv2.fillPoly(mask, [pts.astype(np.int32)], 255)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask[gray < 80] = 0                      # drop dark iris/pupil/lashes
    px = frame[mask > 0].astype(float)
    if len(px) < 15: return None
    b, g, r = px[:, 0].mean(), px[:, 1].mean(), px[:, 2].mean()
    return r / (g + b + 1e-6)                # higher = redder

def worker():
    cap = None
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise RuntimeError("No webcam found, or it is blocked")
        watch(cap)
    except Exception as ex:
        with lock: state["error"] = str(ex)
    finally:
        if cap is not None: cap.release()

def watch(cap):
    mesh = mp.solutions.face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True)
    blinks = collections.deque()             # timestamps of blinks
    red_hist = collections.deque(maxlen=120)
    base_samples, closed = [], False
    start = last_seen = last_tick = time.time()

    while not stop_event.is_set():
        ok, frame = cap.read()
        if not ok: time.sleep(0.5); continue
        now = time.time()
        res = mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        if res.multi_face_landmarks:
            last_seen = now
            h, w = frame.shape[:2]
            lm = res.multi_face_landmarks[0].landmark
            get = lambda ids: np.array([[lm[i].x * w, lm[i].y * h] for i in ids])
            L, R = get(LEFT), get(RIGHT)

            # blink detection
            e = (ear(L) + ear(R)) / 2
            if e < 0.19 and not closed: closed = True
            elif e >= 0.21 and closed:
                closed = False; blinks.append(now)
            while blinks and now - blinks[0] > 60: blinks.popleft()

            # redness (only when eyes open)
            if e > 0.22:
                vals = [v for v in (eye_redness(frame, L), eye_redness(frame, R)) if v]
                if vals:
                    red = float(np.mean(vals))
                    if now - start < CALIBRATION_SEC: base_samples.append(red)
                    else: red_hist.append(red)

        face = (now - last_seen) < 5
        with lock:
            if not face and now - last_seen > AWAY_RESET_SEC:
                state["work_sec"] = 0                       # break detected
            elif face:
                state["work_sec"] += now - last_tick
            last_tick = now
            state["face"] = face
            state["calibrating"] = now - start < CALIBRATION_SEC
            if base_samples and not state["calibrating"] and state["baseline"] is None:
                state["baseline"] = float(np.median(base_samples))
            if now - start > 60 and face:
                state["blinks_per_min"] = len(blinks)
            if red_hist:
                state["redness"] = float(np.median(red_hist))

            warns = []
            if state["work_sec"] > WORK_LIMIT_SEC:
                warns.append("You've been working for over %d hours. Take a break!" % (WORK_LIMIT_SEC // 3600))
            if state["baseline"] and state["redness"] and \
               state["redness"] > state["baseline"] * (1 + REDNESS_INCREASE):
                warns.append("Your eyes are turning red. Take some rest!")
            if state["blinks_per_min"] is not None and state["blinks_per_min"] < LOW_BLINK_PER_MIN:
                warns.append("You're blinking too little. Blink more or look away for 20 seconds.")
            state["warnings"] = warns
        time.sleep(0.1)

app = Flask(__name__)

@app.route("/status")
def status():
    with lock: return jsonify(state)

@app.route("/")
def index(): return render_template_string(PAGE)

PAGE = """
<!doctype html><html><head><meta charset="utf-8"><title>Eye Guard</title>
<style>
 body{font-family:system-ui;background:#10151c;color:#eee;text-align:center;padding:40px}
 .card{max-width:480px;margin:auto;background:#1b2330;padding:24px;border-radius:16px}
 .warn{background:#c0392b;padding:16px;border-radius:12px;margin:12px 0;font-weight:600}
 .ok{color:#2ecc71} .big{font-size:42px;margin:8px}
</style></head><body><div class="card">
 <h1>👁️ Eye Guard</h1>
 <div class="big" id="t">00:00:00</div><div>continuous work time</div>
 <p id="info"></p><div id="w"></div>
 <button onclick="Notification.requestPermission()">Enable notifications</button>
</div>
<script>
let last="";
const beep=()=>{const c=new AudioContext(),o=c.createOscillator();o.connect(c.destination);o.start();setTimeout(()=>o.stop(),400)};
async function tick(){
 const s=await (await fetch('/status')).json();
 const f=n=>String(Math.floor(n)).padStart(2,'0'), t=s.work_sec;
 document.getElementById('t').textContent=f(t/3600)+':'+f(t%3600/60)+':'+f(t%60);
 document.getElementById('info').innerHTML =
   (s.calibrating?'Calibrating your normal eye colour (keep eyes open, face the camera)...<br>':'')+
   (s.face?'<span class=ok>Face detected</span>':'No face detected')+
   ' | Blinks/min: '+(s.blinks_per_min??'-');
 document.getElementById('w').innerHTML=s.warnings.map(x=>'<div class=warn>⚠️ '+x+'</div>').join('');
 const key=s.warnings.join('|');
 if(key&&key!==last){beep();
   if(Notification.permission==='granted')new Notification('Eye Guard',{body:s.warnings[0]});}
 last=key;
}
setInterval(tick,2000);tick();
</script></body></html>
"""

if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    app.run(host="127.0.0.1", port=5050)