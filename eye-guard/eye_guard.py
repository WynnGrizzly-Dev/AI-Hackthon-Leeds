"""Eye Guard 0.1: one window that starts and stops the webcam monitor in retina1.py."""
import sys, threading, tkinter as tk
import retina1 as monitor

VERSION = "0.1"
BG, CARD = "#10151c", "#1b2330"


class EyeGuard:
    def __init__(self):
        self.thread, self.last = None, ""
        self.root = r = tk.Tk()
        r.title(f"Eye Guard {VERSION}")
        r.configure(bg=BG)
        r.resizable(False, False)
        r.geometry("360x350")
        r.protocol("WM_DELETE_WINDOW", self.close)
        self.timer = self.label("00:00:00", 34, True, pady=(18, 0))
        self.label("continuous work time", 10, color="#9aa5b1")
        self.status = self.label("Camera is off", 12, pady=(12, 0))
        self.detail = self.label("", 10, color="#9aa5b1")
        self.warning = tk.Label(r, text="", font=("Segoe UI", 10, "bold"), fg="white",
                                bg=BG, wraplength=320, height=4)
        self.warning.pack(fill="x", padx=14, pady=8)
        self.button = tk.Button(r, text="Start", width=16, font=("Segoe UI", 12, "bold"),
                                bg="#2ecc71", relief="flat", command=self.toggle)
        self.button.pack()
        self.top = tk.BooleanVar(value=True)
        tk.Checkbutton(r, text="Keep on top", variable=self.top, bg=BG, fg="white",
                       selectcolor=CARD, activebackground=BG, activeforeground="white",
                       command=self.set_top).pack(pady=6)
        self.set_top()
        self.update()

    def label(self, text, size, bold=False, color="white", pady=0):
        w = tk.Label(self.root, text=text, bg=BG, fg=color,
                     font=("Segoe UI", size, "bold" if bold else "normal"))
        w.pack(pady=pady)
        return w

    def play_sound(self):
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            else:
                self.root.bell()
        except Exception:
            pass                            # a failed sound must not hide the warning

    def set_top(self):
        self.root.attributes("-topmost", self.top.get())

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def toggle(self):
        if self.running():
            monitor.stop_event.set()
        else:
            monitor.reset()
            self.last = ""
            self.thread = threading.Thread(target=monitor.worker, daemon=True)
            self.thread.start()
        self.refresh()

    def update(self):
        self.refresh()
        self.root.after(500, self.update)

    def refresh(self):
        with monitor.lock:
            s = dict(monitor.state)
        t = int(s["work_sec"])
        self.timer.config(text=f"{t//3600:02d}:{t%3600//60:02d}:{t%60:02d}")
        on, stopping = self.running(), monitor.stop_event.is_set()
        self.button.config(text="Stop" if on else "Start", bg="#e74c3c" if on else "#2ecc71",
                           state="disabled" if on and stopping else "normal")
        if s["error"]:
            text, color = s["error"], "#e74c3c"
        elif not on:
            text, color = "Camera is off", "#9aa5b1"
        elif not s["face"]:
            text, color = "No face seen", "#9aa5b1"
        elif s["calibrating"]:
            text, color = "Calibrating - look at the camera", "#f1c40f"
        else:
            text, color = "Watching your eyes", "#2ecc71"
        self.status.config(text=text, fg=color)
        b = s["blinks_per_min"]
        self.detail.config(text=f"Blinks per minute: {b if on and b is not None else '-'}")
        joined = "\n".join(s["warnings"]) if on else ""
        self.warning.config(text=joined, bg="#c0392b" if joined else BG)
        if joined and joined != self.last:
            self.play_sound()
        self.last = joined

    def close(self):
        monitor.stop_event.set()            # the worker then releases the webcam
        if self.thread:
            self.thread.join(timeout=3)
        self.root.destroy()


def selftest(path):
    """Load the face model on a blank image, without using the webcam."""
    import traceback
    import numpy as np
    try:
        m = monitor.mp.solutions.face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True)
        m.process(np.zeros((480, 640, 3), np.uint8))
        out = "ok"
    except Exception:
        out = traceback.format_exc()
    with open(path, "w") as f:
        f.write(out)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
    else:
        EyeGuard().root.mainloop()
