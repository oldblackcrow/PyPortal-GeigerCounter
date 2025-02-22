# Import necessary libraries
import time
import sys
import board
import displayio
import busio
import digitalio
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text.label import Label
from adafruit_display_shapes.rect import Rect
import adafruit_touchscreen
from adafruit_pyportal import PyPortal
import adafruit_lidarlite
import adafruit_ltr390
from adafruit_button import Button
import storage
import adafruit_sdcard

cwd = ("/"+__file__).rsplit('/', 1)[0]  # Current working directory
sys.path.append(cwd)


# ------------- Pocket Geiger Setup ------------- #
SIGNAL_PIN = board.D3  # Geiger Counter signal pin
HISTORY_LENGTH = 60  # Store last 60 readings (1 min history)
HISTORY_UNIT = 1  # seconds
PROCESS_PERIOD = 0.160  # seconds
K_ALPHA = 53.032  # Calibration constant

# Radiation count variables
radiation_count = 0
count_history = [0] * HISTORY_LENGTH
history_index = 0
history_length = 0
last_process_time = time.monotonic()
last_history_time = time.monotonic()

# Set up digital input pin for Geiger counter
try:
    signal_pin = digitalio.DigitalInOut(SIGNAL_PIN)
    signal_pin.direction = digitalio.Direction.INPUT
    signal_pin.pull = digitalio.Pull.UP
    geiger_found = True
except Exception as e:
    print(f"Geiger sensor not found: {e}")
    geiger_found = False

# LIDAR setup
lidar_found = False
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    lidar = adafruit_lidarlite.LIDARLite(i2c)
    lidar_found = True
except Exception as e:
    print(f"LIDAR sensor not found: {e}")
    lidar_found = False

# UV Sensor setup
uv_sensor_found = False
try:
    ltr = adafruit_ltr390.LTR390(i2c)
    uv_sensor_found = True
except Exception as e:
    print(f"UV sensor not found: {e}")
    uv_sensor_found = False

# ------------- Display & Sound Setup ------------- #
pyportal = PyPortal()
display = board.DISPLAY
display.rotation = 0
splash = displayio.Group()
display.root_group = splash  # Set as active display group

# Sound file for tab switching
TAB_SOUND = "/sounds/tab.wav"

print("Display Test Passed!")



# ------------- TOS-Style UI ------------- #
bg_rect = Rect(0, 0, 320, 240, fill=0x000000)  # Black background
splash.append(bg_rect)

# **Side Panels**
left_panel = Rect(0, 0, 30, 240, fill=0x003366)
right_panel = Rect(290, 0, 40, 240, fill=0x003366)
splash.append(left_panel)
splash.append(right_panel)

# **Blinking "SCANNING" Label**
font_trek = bitmap_font.load_font("fonts/TrekClassic-31.bdf")
scanning_label = Label(font=font_trek, text="SCANNING", color=0xFFFF00, scale=1)
scanning_label.x = 180
scanning_label.y = 20
splash.append(scanning_label)

# **Tab Buttons**
buttons = []
font_greek = bitmap_font.load_font("fonts/Greek03-Regular-25.bdf")
font_trek = bitmap_font.load_font("fonts/LeagueSpartan-Bold-16.bdf")

button_radiation = Button(x=10, y=200, width=100, height=30,
                          label="γ", label_font=font_greek, fill_color=0xFFFFFF)
button_distance = Button(x=115, y=200, width=100, height=30,
                         label="Prox", label_font=font_trek, fill_color=0xFFFFFF)
button_uv = Button(x=220, y=200, width=90, height=30,
                   label="Δ", label_font=font_greek, fill_color=0xFFFFFF)

buttons.append(button_radiation)
buttons.append(button_distance)
buttons.append(button_uv)
splash.append(button_radiation)
splash.append(button_distance)
splash.append(button_uv)

# ------------- UI Containers (Only This Switches) ------------- #
content_group = displayio.Group()
splash.append(content_group)

# ------------- Radiation Tab UI ------------- #
view_radiation = displayio.Group()
radiation_label = Label(font=font_trek, text="CPM: --", color=0x00FFFF, scale=1)
radiation_label.x = 70
radiation_label.y = 80
view_radiation.append(radiation_label)

dose_label = Label(font=font_trek, text="DOSE: -- µSv/h", color=0xFFFF00, scale=1)
dose_label.x = 70
dose_label.y = 100
view_radiation.append(dose_label)

# ------------- Distance Tab UI (Prox) ------------- #
view_distance = displayio.Group()
distance_label = Label(font=font_trek, text="Distance: -- m", color=0x00FFFF, scale=1)
distance_label.x = 70
distance_label.y = 80
view_distance.append(distance_label)

no_data_label = Label(font=font_trek, text="Sensor not detected.", color=0xFF0000, scale=1)
no_data_label.x = 70
no_data_label.y = 130
view_distance.append(no_data_label)

# ------------- UV Sensor Tab UI (Δ) ------------- #
view_uv = displayio.Group()
uv_index_label = Label(font=font_trek, text="UV Index: --", color=0x00FFFF, scale=1)
uv_index_label.x = 70
uv_index_label.y = 80
view_uv.append(uv_index_label)

uv_intensity_label = Label(font=font_trek, text="UV I: --", color=0xFFFF00, scale=1)
uv_intensity_label.x = 70
uv_intensity_label.y = 100
view_uv.append(uv_intensity_label)

no_uv_label = Label(font=font_trek, text="No sensor detected.", color=0xFF0000, scale=1)
no_uv_label.x = 70
no_uv_label.y = 130
view_uv.append(no_uv_label)

# ------------- Radiation Processing ------------- #
def process_radiation():
    global last_process_time, last_history_time, radiation_count, history_index, history_length

    current_time = time.monotonic()

    if geiger_found and not signal_pin.value:  
        radiation_count += 1

    if current_time - last_history_time >= HISTORY_UNIT:
        last_history_time = current_time
        count_history[history_index] = radiation_count
        radiation_count = 0
        history_index = (history_index + 1) % HISTORY_LENGTH
        history_length = min(history_length + 1, HISTORY_LENGTH)

def calculate_cpm():
    return (sum(count_history) * 60) / (history_length * HISTORY_UNIT) if history_length else 0

def calculate_uSvh():
    return calculate_cpm() / K_ALPHA if geiger_found else 0

def update_display():
    scanning_label.color = 0xFFFF00 if int(time.monotonic() % 2) == 0 else 0x000000
    display.refresh()  # Force screen update

    if view_live == "Radiation":
        radiation_label.text = f"CPM: {calculate_cpm():.1f}"
        dose_label.text = f"DOSE: {calculate_uSvh():.3f} µSv/h"

def switch_view(new_view):
    global view_live
    pyportal.play_file(TAB_SOUND)
    if content_group:
        content_group.pop()
    view_live = new_view
    content_group.append(view_radiation if new_view == "Radiation" else view_distance if new_view == "Distance" else view_uv)
    update_display()

# ------------- Load and display the Star Trek delta logo AFTER defining all views -------------
try:
    print("Attempting to load delta.bmp...")
    delta_bitmap = displayio.OnDiskBitmap("/delta.bmp")

    # Create separate instances of delta logo for each tab
    delta_radiation = displayio.TileGrid(delta_bitmap, pixel_shader=delta_bitmap.pixel_shader)
    delta_distance = displayio.TileGrid(delta_bitmap, pixel_shader=delta_bitmap.pixel_shader)
    delta_uv = displayio.TileGrid(delta_bitmap, pixel_shader=delta_bitmap.pixel_shader)

    # Position them in the lower-right corner
    delta_radiation.x = delta_distance.x = delta_uv.x = 260  # Adjust as needed
    delta_radiation.y = delta_distance.y = delta_uv.y = 140  # Adjust as needed

    print("✅ Delta logo loaded successfully!")
    print(f"Bitmap size: {delta_bitmap.width}x{delta_bitmap.height}")

    # Append unique instances to each tab
    view_radiation.append(delta_radiation)
    view_distance.append(delta_distance)
    view_uv.append(delta_uv)

    print("✅ Delta logo added to all tab screens!")

except Exception as e:
    print(f"❌ Failed to load delta.bmp: {e}")

# ------------- Main Loop ------------- #
view_live = "Radiation"
content_group.append(view_radiation)

while True:
    touch = pyportal.touchscreen.touch_point
    process_radiation()
    if touch:
        for i, button in enumerate(buttons):
            if button.contains(touch):
                switch_view(["Radiation", "Distance", "UV"][i])
    update_display()
    time.sleep(0.1)
