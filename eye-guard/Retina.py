import tkinter as tk, json, subprocess, sys, urllib.request

URL = "http://127.0.0.1:5050/status"
W, H = 230, 78

root = tk.Tk()
root.title("Eye Guard")
root.attributes("-topmost", True)          # always on top
root.resizable(False, False)
sw = root.winfo_screenwidth()
root.geometry(f"{W}x{H}+{sw - W - 15}+40")  # top-right corner

timer = tk.Label(root, text="--:--:--", font=("Helvetica", 20, "bold"))
timer.pack(pady=(6, 0))
msg = tk.Label(root, text="starting...", font=("Helvetica", 10), wraplength=W - 10)
msg.pack()

last = ""

def play_sound():
    try:
        if sys.platform == "win32":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        elif sys.platform == "darwin":
            subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
        else:
            root.bell()
    except Exception:
        pass                                    # a failed sound must not hide the warning


def update():
    global last
    try:
        s = json.load(urllib.request.urlopen(URL, timeout=2))
        t = int(s["work_sec"])
        timer.config(text=f"{t//3600:02d}:{t%3600//60:02d}:{t%60:02d}")
        if s["warnings"]:
            text = s["warnings"][0]
            color = "#e74c3c"
            if text != last:                # new warning -> sound
                play_sound()
            last = text
        else:
            last = ""
            if s["calibrating"]:
                text, color = "Calibrating...", "#f1c40f"
            elif not s["face"]:
                text, color = "No face seen", "#95a5a6"
            else:
                text, color = f"Eyes OK  |  blinks/min: {s['blinks_per_min'] or '-'}", "#2ecc71"
        root.config(bg=color); timer.config(bg=color); msg.config(text=text, bg=color)
    except Exception:
        msg.config(text="retina1.py not running?")
    root.after(2000, update)

update()
root.mainloop()