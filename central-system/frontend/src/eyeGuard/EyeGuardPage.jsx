import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { LEFT, RIGHT, createMonitor, ear, eyeRedness } from './monitor';

// Face model files are copied from node_modules into public/face_mesh (see package.json).
let scriptPromise;
function loadFaceMesh() {
  scriptPromise ??= new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = '/face_mesh/face_mesh.js';
    el.onload = () => resolve(window.FaceMesh);
    el.onerror = () => { scriptPromise = undefined; reject(new Error('Could not load the face model.')); };
    document.head.append(el);
  });
  return scriptPromise;
}

function beep(audio) {
  const o = audio.createOscillator();
  const g = audio.createGain();
  g.gain.value = 0.2;
  o.connect(g).connect(audio.destination);
  o.start();
  o.stop(audio.currentTime + 0.4);
}

const IDLE = { work: 0, face: false, calibrating: false, blinksPerMin: null, warnings: [] };
const two = (n) => String(Math.floor(n)).padStart(2, '0');

export function EyeGuardPage() {
  const video = useRef(null);
  const session = useRef(null);
  const [phase, setPhase] = useState('off'); // off | starting | on
  const [error, setError] = useState('');
  const [s, setS] = useState(IDLE);

  const stop = useCallback(() => {
    const cur = session.current;
    session.current = null;
    if (cur) {
      cur.dead = true;
      clearTimeout(cur.timer);
      cur.stream?.getTracks().forEach((t) => t.stop());
      cur.mesh?.close();
      cur.audio?.close();
    }
    if (video.current) video.current.srcObject = null;
    setPhase('off');
  }, []);
  useEffect(() => stop, [stop]);

  const start = async () => {
    const cur = { dead: false };
    session.current = cur;
    setError(''); setS(IDLE); setPhase('starting');
    try {
      cur.audio = new AudioContext();
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
      cur.stream = stream;
      if (cur.dead) { stream.getTracks().forEach((t) => t.stop()); return; }
      stream.getVideoTracks()[0].onended = () => {
        if (!cur.dead) { stop(); setError('The camera was disconnected.'); }
      };
      const FaceMesh = await loadFaceMesh();
      if (cur.dead) return;
      const mesh = new FaceMesh({ locateFile: (f) => `/face_mesh/${f}` });
      cur.mesh = mesh;
      mesh.setOptions({ maxNumFaces: 1, refineLandmarks: true });
      let landmarks = null;
      mesh.onResults((r) => { landmarks = r.multiFaceLandmarks?.[0] ?? null; });
      const el = video.current;
      el.srcObject = stream;
      await el.play();
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d', { willReadFrequently: true });

      let tick = null, lastWarning = '';
      const loop = async () => {
        if (cur.dead) return;
        try {
          if (el.paused) await el.play(); // some browsers pause the video in a hidden tab
          await mesh.send({ image: el });
          if (cur.dead) return;
          const now = performance.now() / 1000;
          tick ??= createMonitor(now); // calibration starts once the model is ready
          let sample = null;
          if (landmarks) {
            const w = canvas.width = el.videoWidth, h = canvas.height = el.videoHeight;
            ctx.drawImage(el, 0, 0);
            const get = (ids) => ids.map((i) => ({ x: landmarks[i].x * w, y: landmarks[i].y * h }));
            const L = get(LEFT), R = get(RIGHT);
            const reds = [eyeRedness(ctx, L), eyeRedness(ctx, R)].filter(Boolean);
            sample = { ear: (ear(L) + ear(R)) / 2, redness: reds.length ? reds.reduce((a, b) => a + b) / reds.length : null };
          }
          const next = tick(now, sample, document.hidden);
          const key = next.warnings.join('|');
          if (key && key !== lastWarning) beep(cur.audio);
          lastWarning = key;
          setS(next);
          setPhase('on');
          cur.timer = setTimeout(loop, 60);
        } catch (e) {
          if (!cur.dead) { stop(); setError(e.message || 'Eye Guard stopped unexpectedly.'); }
        }
      };
      loop();
    } catch (e) {
      if (cur.dead) return;
      stop();
      setError(e.name === 'NotAllowedError' ? 'Camera access was blocked. Allow it in your browser, then try again.'
        : e.name === 'NotFoundError' ? 'No webcam was found.' : e.message || 'Could not start the camera.');
    }
  };

  const on = phase === 'on';
  const status = phase === 'starting' ? 'Starting…' : !on ? 'Camera is off'
    : !s.face ? 'No face seen' : s.calibrating ? 'Calibrating: look at the camera' : 'Watching your eyes';
  const muted = { color: '#c7aea5', margin: '0 0 12px' };
  return (
    <main style={{ minHeight: '100vh', boxSizing: 'border-box', background: '#18100e', color: '#f8ede6', fontFamily: 'Inter, Arial, sans-serif', padding: '20px clamp(16px, 4vw, 64px)' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <strong style={{ letterSpacing: '0.12em' }}>RETINA<span style={{ color: '#e45b45' }}>TRANSFORM</span></strong>
        <Link to="/" style={{ color: '#eb8c73' }}>Back to main site</Link>
      </header>
      <section style={{ maxWidth: 520, margin: '32px auto', textAlign: 'center' }}>
        <h1 style={{ margin: '0 0 8px' }}>Eye Guard</h1>
        <p style={muted}>Reminds you to rest your eyes. Video is processed on this device and is not uploaded or saved.</p>
        <video ref={video} muted playsInline style={{ width: '100%', borderRadius: 12, transform: 'scaleX(-1)', display: phase === 'off' ? 'none' : 'block' }} />
        <div style={{ fontSize: 48, fontVariantNumeric: 'tabular-nums', marginTop: 16 }}>{two(s.work / 3600)}:{two((s.work % 3600) / 60)}:{two(s.work % 60)}</div>
        <p style={muted}>continuous work time</p>
        <p role="status" style={{ fontWeight: 600 }}>{status}</p>
        <p style={muted}>Blinks per minute: {on && s.blinksPerMin !== null ? s.blinksPerMin : '-'}</p>
        <div role="alert">
          {error && <p style={{ background: '#6b1f1a', padding: 14, borderRadius: 10 }}>{error}</p>}
          {on && s.warnings.map((w) => <p key={w} style={{ background: '#a72c25', padding: 14, borderRadius: 10, fontWeight: 600 }}>{w}</p>)}
        </div>
        <button type="button" onClick={phase === 'off' ? start : stop} style={{ padding: '14px 40px', color: 'white', background: phase === 'off' ? '#237a49' : '#a72c25', border: 0, borderRadius: 8, fontSize: 16, cursor: 'pointer' }}>
          {phase === 'off' ? 'Start camera' : 'Stop camera'}
        </button>
        <p style={{ ...muted, fontSize: 13, marginTop: 20 }}>Keep this tab visible: blinks cannot be counted in a background tab. This is a wellbeing reminder, not a medical measurement.</p>
      </section>
    </main>
  );
}
