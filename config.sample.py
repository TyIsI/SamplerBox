#########################################
# LOCAL
# CONFIG
#########################################

# change this number to use another soundcard
AUDIO_DEVICE_ID = 0

# The main directory containing the sample-sets. Example: "/media/" to look for samples on a USB stick / SD card
MAIN_SAMPLES_DIR = "/media/usb"
# The backup directory containing the sample-sets. Example: "/media/" to look for samples on a USB stick / SD card
BACKUP_SAMPLES_DIR = "/samples"

# This can be set higher, but 80 is a safe value
MAX_POLYPHONY = 80

# Set to True to use momentary buttons (connected to RaspberryPi's GPIO pins) to change preset
USE_BUTTONS = False
# Up Button
BUTTON_UP = 13
# Down button
BUTTON_DOWN = 26

# Set to True to use a 7-segment display via I2C
USE_I2C_7SEGMENTDISPLAY = False

# Use a 16x2 display
USE_I2C_DISPLAY_16X2 = False
# I2C display address
I2C_DISPLAY_ADDRESS = 0x3F
# I2C port
I2C_DISPLAY_PORT = 1

# Set to True to enable MIDI IN via SerialPort (e.g. RaspberryPi's GPIO UART pins)
USE_SERIALPORT_MIDI = False

# Flashing LED after successful boot, only works on RPi/Linux
USE_SYSTEMLED = False
