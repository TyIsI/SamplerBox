#
#  SamplerBox
#
#  author:    Joseph Ernest (twitter: @JosephErnest, mail: contact@samplerbox.org)
#  url:       http://www.samplerbox.org/
#  license:   Creative Commons ShareAlike 3.0 (http://creativecommons.org/licenses/by-sa/3.0/)
#
#  samplerbox.py: Main file (now requiring at least Python 3.7)
#

#########################################
# IMPORT
# MODULES
#########################################

from config import *
import wave
import time
import numpy
import os
import re
import sounddevice
import threading
from chunk import Chunk
import struct
import rtmidi_python as rtmidi
import samplerbox_audio

#########################################
# Variables
#########################################

FADEOUTLENGTH = 30000
# by default, float64
FADEOUT = numpy.linspace(1., 0., FADEOUTLENGTH)
FADEOUT = numpy.power(FADEOUT, 6)
FADEOUT = numpy.append(FADEOUT, numpy.zeros(
    FADEOUTLENGTH, numpy.float32)).astype(numpy.float32)
SPEED = numpy.power(2, numpy.arange(0.0, 84.0)/12).astype(numpy.float32)

samples = {}
playingnotes = {}
sustainplayingnotes = []
sustain = False
playingsounds = []
globalvolume = 10 ** (-12.0/20)  # -12dB default global volume
globaltranspose = 0

preset = 0
presetName = "Initializing"

LoadingThread = None
LoadingInterrupt = False

NOTES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]

#########################################
# SLIGHT MODIFICATION OF PYTHON'S WAVE MODULE
# TO READ CUE MARKERS & LOOP MARKERS
#########################################


class waveread(wave.Wave_read):
    def initfp(self, file):
        self._convert = None
        self._soundpos = 0
        self._cue = []
        self._loops = []
        self._ieee = False
        self._file = Chunk(file, bigendian=0)

        if self._file.getname() != b'RIFF':
            raise IOError('file does not start with RIFF id')

        if self._file.read(4) != b'WAVE':
            raise IOError('not a WAVE file')

        self._fmt_chunk_read = 0
        self._data_chunk = None

        while 1:
            self._data_seek_needed = 1

            try:
                chunk = Chunk(self._file, bigendian=0)
            except EOFError:
                break

            chunkname = chunk.getname()

            if chunkname == b'fmt ':
                self._read_fmt_chunk(chunk)
                self._fmt_chunk_read = 1
            elif chunkname == b'data':
                if not self._fmt_chunk_read:
                    raise IOError('data chunk before fmt chunk')

                self._data_chunk = chunk
                self._nframes = chunk.chunksize // self._framesize
                self._data_seek_needed = 0
            elif chunkname == b'cue ':
                numcue = struct.unpack('<i', chunk.read(4))[0]

                for i in range(numcue):
                    id, position, datachunkid, chunkstart, blockstart, sampleoffset = struct.unpack(
                        '<iiiiii', chunk.read(24))
                    self._cue.append(sampleoffset)
            elif chunkname == b'smpl':
                manuf, prod, sampleperiod, midiunitynote, midipitchfraction, smptefmt, smpteoffs, numsampleloops, samplerdata = struct.unpack(
                    '<iiiiiiiii', chunk.read(36))

                for i in range(numsampleloops):
                    cuepointid, type, start, end, fraction, playcount = struct.unpack(
                        '<iiiiii', chunk.read(24))
                    self._loops.append([start, end])

            chunk.skip()

        if not self._fmt_chunk_read or not self._data_chunk:
            raise IOError('fmt chunk and/or data chunk missing')

    def getmarkers(self):
        return self._cue

    def getloops(self):
        return self._loops

#########################################
# MIXER CLASSES
#########################################


class PlayingSound:
    def __init__(self, sound, note):
        self.sound = sound
        self.pos = 0
        self.fadeoutpos = 0
        self.isfadeout = False
        self.note = note

    def fadeout(self, i):
        self.isfadeout = True

    def stop(self):
        try:
            playingsounds.remove(self)
        except:
            pass


class Sound:
    def __init__(self, filename, midinote, velocity):
        wf = waveread(filename)
        self.fname = filename
        self.midinote = midinote
        self.velocity = velocity

        if wf.getloops():
            self.loop = wf.getloops()[0][0]
            self.nframes = wf.getloops()[0][1] + 2
        else:
            self.loop = -1
            self.nframes = wf.getnframes()

        self.data = self.frames2array(wf.readframes(
            self.nframes), wf.getsampwidth(), wf.getnchannels())
        wf.close()

    def play(self, note):
        snd = PlayingSound(self, note)
        playingsounds.append(snd)

        return snd

    def frames2array(self, data, sampwidth, numchan):
        if sampwidth == 2:
            npdata = numpy.frombuffer(data, dtype=numpy.int16)
        elif sampwidth == 3:
            npdata = samplerbox_audio.binary24_to_int16(data, len(data)//3)

        if numchan == 1:
            npdata = numpy.repeat(npdata, 2)

        return npdata


#########################################
# AUDIO AND MIDI CALLBACKS
#########################################

def AudioCallback(outdata, frame_count, time_info, status):
    global playingsounds

    rmlist = []
    playingsounds = playingsounds[-MAX_POLYPHONY:]
    b = samplerbox_audio.mixaudiobuffers(
        playingsounds, rmlist, frame_count, FADEOUT, FADEOUTLENGTH, SPEED)

    for e in rmlist:
        try:
            playingsounds.remove(e)
        except:
            pass

    b *= globalvolume
    outdata[:] = b.reshape(outdata.shape)


def MidiCallback(message, time_stamp):
    global playingnotes, sustain, sustainplayingnotes
    global preset

    messagetype = message[0] >> 4
    messagechannel = (message[0] & 15) + 1
    note = message[1] if len(message) > 1 else None
    midinote = note
    velocity = message[2] if len(message) > 2 else None

    if messagetype == 9 and velocity == 0:
        messagetype = 8

    if messagetype == 9:    # Note on
        midinote += globaltranspose

        try:
            playingnotes.setdefault(midinote, []).append(
                samples[midinote, velocity].play(midinote))
        except:
            pass
    elif messagetype == 8:  # Note off
        midinote += globaltranspose

        if midinote in playingnotes:
            for n in playingnotes[midinote]:
                if sustain:
                    sustainplayingnotes.append(n)
                else:
                    n.fadeout(50)

            playingnotes[midinote] = []
    elif messagetype == 12:  # Program change
        print('Program change ' + str(note))
        preset = note
        LoadSamples()
    elif (messagetype == 11) and (note == 64) and (velocity < 64):  # sustain pedal off
        for n in sustainplayingnotes:
            n.fadeout(50)

        sustainplayingnotes = []
        sustain = False
    elif (messagetype == 11) and (note == 64) and (velocity >= 64):  # sustain pedal on
        sustain = True

#########################################
# LOAD SAMPLES
#########################################


def LoadSamples():
    global LoadingThread
    global LoadingInterrupt

    if LoadingThread:
        LoadingInterrupt = True
        LoadingThread.join()
        LoadingThread = None

    LoadingInterrupt = False
    LoadingThread = threading.Thread(target=ActuallyLoad)
    LoadingThread.daemon = True
    LoadingThread.start()


def ActuallyLoad():
    global preset, presetName
    global samples
    global playingsounds
    global globalvolume, globaltranspose

    playingsounds = []
    samples = {}
    globalvolume = 10 ** (-12.0/20)  # -12dB default global volume
    globaltranspose = 0
    # use current folder (containing 0 Saw) if no user media containing samples has been found
    samplesdir = MAIN_SAMPLES_DIR if os.listdir(
        MAIN_SAMPLES_DIR) else BACKUP_SAMPLES_DIR
    basename = next((f for f in os.listdir(samplesdir) if f.startswith(
        "%d " % preset)), None)      # or next(glob.iglob("blah*"), None)

    presetName = basename

    if basename:
        dirname = os.path.join(samplesdir, basename)

    if not basename:
        print('Preset empty: %s' % preset)
        display("E%03d" % preset)

        return

    print('Preset loading: %s (%s)' % (preset, basename))
    display("L%03d" % preset)
    definitionfname = os.path.join(dirname, "definition.txt")

    if os.path.isfile(definitionfname):
        with open(definitionfname, 'r') as definitionfile:
            for i, pattern in enumerate(definitionfile):
                try:
                    if r'%%volume' in pattern:        # %%paramaters are global parameters
                        globalvolume *= 10 ** (float(pattern.split('=')
                                               [1].strip()) / 20)

                        continue
                    if r'%%transpose' in pattern:
                        globaltranspose = int(pattern.split('=')[1].strip())

                        continue

                    defaultparams = {'midinote': '0',
                                     'velocity': '127', 'notename': ''}

                    if len(pattern.split(',')) > 1:
                        defaultparams.update(dict([item.split('=') for item in pattern.split(',', 1)[
                                             1].replace(' ', '').replace('%', '').split(',')]))

                    pattern = pattern.split(',')[0]
                    # note for Python 3.7+: "%" is no longer escaped with "\"
                    pattern = re.escape(pattern.strip())
                    pattern = pattern.replace(r"%midinote", r"(?P<midinote>\d+)").replace(r"%velocity", r"(?P<velocity>\d+)")\
                                     .replace(r"%notename", r"(?P<notename>[A-Ga-g]#?[0-9])").replace(r"\*", r".*?").strip()    # .*? => non greedy

                    for fname in os.listdir(dirname):
                        if LoadingInterrupt:
                            return

                        m = re.match(pattern, fname)

                        if m:
                            info = m.groupdict()
                            midinote = int(
                                info.get('midinote', defaultparams['midinote']))
                            velocity = int(
                                info.get('velocity', defaultparams['velocity']))
                            notename = info.get(
                                'notename', defaultparams['notename'])

                            if notename:
                                midinote = NOTES.index(
                                    notename[:-1].lower()) + (int(notename[-1])+2) * 12

                            samples[midinote, velocity] = Sound(
                                os.path.join(dirname, fname), midinote, velocity)
                except:
                    print("Error in definition file, skipping line %s." % (i+1))
    else:
        for midinote in range(0, 127):
            if LoadingInterrupt:
                return

            file = os.path.join(dirname, "%d.wav" % midinote)

            if os.path.isfile(file):
                samples[midinote, 127] = Sound(file, midinote, 127)

    initial_keys = set(samples.keys())

    for midinote in range(128):
        lastvelocity = None

        for velocity in range(128):
            if (midinote, velocity) not in initial_keys:
                samples[midinote, velocity] = lastvelocity
            else:
                if not lastvelocity:
                    for v in range(velocity):
                        samples[midinote, v] = samples[midinote, velocity]

                lastvelocity = samples[midinote, velocity]

        if not lastvelocity:
            for velocity in range(128):
                try:
                    samples[midinote, velocity] = samples[midinote-1, velocity]
                except:
                    pass

    if len(initial_keys) > 0:
        print('Preset loaded: ' + str(preset))
        display("%04d" % preset)
    else:
        print('Preset empty: ' + str(preset))
        display("E%03d" % preset)


#########################################
# Main program execution
#########################################
if __name__ == "__main__":

    #########################################
    # OPEN AUDIO DEVICE
    #########################################

    try:
        sd = sounddevice.OutputStream(device=AUDIO_DEVICE_ID, blocksize=512,
                                      samplerate=44100, channels=2, dtype='int16', callback=AudioCallback)
        sd.start()
        print('Opened audio device #%i' % AUDIO_DEVICE_ID)
    except:
        print('Invalid audio device #%i' % AUDIO_DEVICE_ID)
        exit(1)

    #########################################
    # BUTTONS THREAD (RASPBERRY PI GPIO)
    #########################################

    if USE_BUTTONS:
        import RPi.GPIO as GPIO

        lastbuttontime = 0

        def Buttons():
            global preset, lastbuttontime

            GPIO.setmode(GPIO.BCM)
            GPIO.setup(BUTTON_UP, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(BUTTON_DOWN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            while True:
                now = time.time()

                if not GPIO.input(BUTTON_DOWN) and (now - lastbuttontime) > 0.2:
                    lastbuttontime = now
                    preset -= 1

                    if preset < 0:
                        preset = 127

                    LoadSamples()
                elif not GPIO.input(BUTTON_UP) and (now - lastbuttontime) > 0.2:
                    lastbuttontime = now
                    preset += 1

                    if preset > 127:
                        preset = 0

                    LoadSamples()

                time.sleep(0.020)

        ButtonsThread = threading.Thread(target=Buttons)
        ButtonsThread.daemon = True
        ButtonsThread.start()

    #########################################
    # DISPLAY
    #########################################

    if USE_I2C_DISPLAY_16X2:
        from RPLCD import i2c

        lcd = i2c.CharLCD('PCF8574', I2C_DISPLAY_ADDRESS,
                          port=I2C_DISPLAY_PORT, charmap='A00', cols=16, rows=2)

        def display(s):
            global presetName

            lcd.clear()

            if presetName is not None:
                lcd.write_string(presetName)
            else:
                lcd.write_string("----")

            lcd.crlf()

            code = s[0]

            if code == "L":
                lcd.write_string("Loading")
            elif code == "E":
                lcd.write_string("Error loading")
            elif code == "-":
                lcd.write_string("-")
            else:
                lcd.write_string("Ready")

        display('----')
        time.sleep(0.5)
    elif USE_I2C_7SEGMENTDISPLAY:  # requires: 1) i2c-dev in /etc/modules and 2) dtparam=i2c_arm=on in /boot/config.txt
        import smbus

        bus = smbus.SMBus(1)     # using I2C

        def display(s):
            for k in '\x76\x79\x00' + s:     # position cursor at 0
                try:
                    bus.write_byte(0x71, ord(k))
                except:
                    try:
                        bus.write_byte(0x71, ord(k))
                    except:
                        pass

                time.sleep(0.002)

        display('----')
        time.sleep(0.5)
    else:
        def display(s):
            pass

    #########################################
    # MIDI IN via SERIAL PORT
    #########################################

    if USE_SERIALPORT_MIDI:
        import serial

        ser = serial.Serial('/dev/ttyAMA0', baudrate=31250)

        def MidiSerialCallback():
            message = [0, 0, 0]

            while True:
                i = 0

                while i < 3:
                    data = ord(ser.read(1))  # read a byte

                    if data >> 7 != 0:
                        i = 0      # status byte!   this is the beginning of a midi message: http://www.midi.org/techspecs/midimessages.php

                    message[i] = data
                    i += 1

                    # program change: don't wait for a third byte: it has only 2 bytes
                    if i == 2 and message[0] >> 4 == 12:
                        message[2] = 0
                        i = 3

                MidiCallback(message, None)

        MidiThread = threading.Thread(target=MidiSerialCallback)
        MidiThread.daemon = True
        MidiThread.start()

    #########################################
    # LOAD FIRST SOUNDBANK
    #########################################

    LoadSamples()

    #########################################
    # SYSTEM LED
    #########################################

    if USE_SYSTEMLED:
        os.system("modprobe ledtrig_heartbeat")
        os.system("echo heartbeat >/sys/class/leds/led0/trigger")

    #########################################
    # MIDI DEVICES DETECTION
    # MAIN LOOP
    #########################################

    midi_in = [rtmidi.MidiIn(b'in')]
    previous = []

    while True:
        for port in midi_in[0].ports:
            if port not in previous and b'Midi Through' not in port:
                midi_in.append(rtmidi.MidiIn(b'in'))
                midi_in[-1].callback = MidiCallback
                midi_in[-1].open_port(port)

                print('Opened MIDI: ' + str(port))

        previous = midi_in[0].ports
        time.sleep(2)
