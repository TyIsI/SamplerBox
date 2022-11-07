#########################################
# LOCAL
# CONFIG
#########################################

AUDIO_DEVICE_ID = 0                     # change this number to use another soundcard
SAMPLES_DIR = "/samples"                # The root directory containing the sample-sets. Example: "/media/" to look for samples on a USB stick / SD card
MAX_POLYPHONY = 80                      # This can be set higher, but 80 is a safe value
USE_BUTTONS = False                     # Set to True to use momentary buttons (connected to RaspberryPi's GPIO pins) to change preset
BUTTON_UP = 13                          # Up Button
BUTTON_DOWN = 26                        # Down button
USE_I2C_7SEGMENTDISPLAY = False         # Set to True to use a 7-segment display via I2C
USE_I2C_DISPLAY_16X2 = False            # Use a 16x2 display
I2C_DISPLAY_ADDRESS = 0x3F              # I2C display address
I2C_DISPLAY_PORT = 1                    # I2C port
USE_SERIALPORT_MIDI = False             # Set to True to enable MIDI IN via SerialPort (e.g. RaspberryPi's GPIO UART pins)
USE_SYSTEMLED = False                   # Flashing LED after successful boot, only works on RPi/Linux
