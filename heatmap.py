import serial
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ==========================================
# CONFIGURATION
# ==========================================

SIMULATE = True      # True = fake moving blob, False = read ESP32
PORT = "COM9"
BAUD = 115200

ROWS = 12
COLS = 24

AMBIENT = 22.0
PEAK_TEMP = 38.0

# Blob motion (in frames; the animation runs at ~10 fps)
ENTER_FRAMES = 40    # slide in from the right
HOLD_FRAMES = 20     # stay in the middle
LEAVE_FRAMES = 40    # slide back out to the right
IDLE_FRAMES = 30     # empty scene before the next pass

START_X = COLS + 5   # off-screen right
HOLD_X = COLS * 0.45 # where it stops
BLOB_SIGMA_X = 3.5
BLOB_SIGMA_Y = 2.5

# ==========================================
# BLOB SIMULATION
# ==========================================

Y, X = np.mgrid[0:ROWS, 0:COLS].astype(float)
rng = np.random.default_rng()
tick = 0

def smoothstep(t):
    return t * t * (3 - 2 * t)

def blob_position(frame):
    """Returns the blob's x-position and strength (0..1) for this frame."""
    cycle = ENTER_FRAMES + HOLD_FRAMES + LEAVE_FRAMES + IDLE_FRAMES
    f = frame % cycle

    if f < ENTER_FRAMES:
        t = smoothstep(f / ENTER_FRAMES)
        return START_X + (HOLD_X - START_X) * t, 1.0
    f -= ENTER_FRAMES

    if f < HOLD_FRAMES:
        return HOLD_X, 1.0
    f -= HOLD_FRAMES

    if f < LEAVE_FRAMES:
        t = smoothstep(f / LEAVE_FRAMES)
        return HOLD_X + (START_X - HOLD_X) * t, 1.0

    return START_X, 0.0   # idle

def simulated_frame():
    global tick
    tick += 1

    cx, strength = blob_position(tick)
    cy = ROWS / 2 + 0.8 * np.sin(tick / 12)       # slight vertical drift

    blob = np.exp(
        -(((X - cx) / BLOB_SIGMA_X) ** 2 + ((Y - cy) / BLOB_SIGMA_Y) ** 2)
    )

    noise = rng.normal(0, 0.25, (ROWS, COLS))
    return AMBIENT + (PEAK_TEMP - AMBIENT) * blob * strength + noise

# ==========================================
# CONNECT TO ESP32
# ==========================================

ser = None
if not SIMULATE:
    print(f"Connecting to ESP32 on {PORT}...")
    ser = serial.Serial(PORT, BAUD, timeout=2)
    ser.reset_input_buffer()
    print("Connected! Starting heatmap...")
else:
    print("Simulation mode: moving warm blob...")

# ==========================================
# CREATE HEATMAP WINDOW
# ==========================================

plt.ion()
fig, ax = plt.subplots(figsize=(10, 6))

heatmap = ax.imshow(
    np.full((ROWS, COLS), AMBIENT),
    cmap="inferno",
    vmin=20,
    vmax=50,
    interpolation="bilinear",
    aspect="auto",
)

colorbar = fig.colorbar(heatmap, ax=ax)
colorbar.set_label("Simulated Temperature (°C)")

ax.set_title("ESP32 — Live Infrared Heatmap")
ax.set_xlabel("Horizontal Position")
ax.set_ylabel("Vertical Position")

status_text = ax.text(
    0.02, 0.97, "Waiting for temperature data...",
    transform=ax.transAxes, color="white", verticalalignment="top",
    bbox=dict(facecolor="black", alpha=0.6),
)

# ==========================================
# READ TEMPERATURE DATA (serial mode)
# ==========================================

def read_frame():
    rows = []
    while True:
        line = ser.readline().decode("utf-8", errors="ignore").strip()

        if not line:
            return None

        if line == "END":
            if len(rows) == ROWS:
                frame = np.array(rows, dtype=float)
                if frame.shape == (ROWS, COLS):
                    return frame
            rows = []
            continue

        try:
            values = [float(v) for v in line.split(",")]
            if len(values) == COLS:
                rows.append(values)
            else:
                rows = []
        except ValueError:
            rows = []

# ==========================================
# UPDATE HEATMAP
# ==========================================

def update(_frame_number):
    frame = simulated_frame() if SIMULATE else read_frame()

    if frame is not None:
        heatmap.set_data(frame)
        status_text.set_text(
            f"MIN: {frame.min():.1f} °C   "
            f"MAX: {frame.max():.1f} °C   "
            f"AVG: {frame.mean():.1f} °C"
        )
    return heatmap, status_text

# ==========================================
# START LIVE DISPLAY
# ==========================================

animation = FuncAnimation(fig, update, interval=100, blit=False, cache_frame_data=False)

try:
    plt.tight_layout()
    plt.show(block=True)
finally:
    if ser:
        ser.close()