# sample script to use Link-to-Py/Carabiner to control an AbletonLink Session
#
# Desktop MPC v2.10 does not issue transport commands, but can output a MMC.
# This script listens for MMC commands and starts/stops Link appropriately.

import LinkToPy
import time
import mido
import sys

delta_us = None
playing = None
inport = None

def callback_status(cb):
    global delta_us, playing

    # monotonic_us = time.monotonic_ns() / 1000  # would be better but not supported :-(
    monotonic_us = int(time.monotonic() * 1000000)
 
    computed_us = cb['start'] + (1000000 * ((cb['beat'] - 1) * 60.0 / cb['bpm']))
    delta_us = computed_us - monotonic_us

    # print(cb)
    # print(monotonic_us, computed_us, delta_us)

    if 'playing' in cb:
        if cb['playing'] == False:
            playing = False
        else:
            playing = True

# ---------------------------------------------
# Find and open midi port to receive MMC on.
# I use a virtual port of 'loopMIDI'

midiname = "loopMIDI"

if sys.platform == 'win32':
    mido.set_backend('mido.backends.rtmidi')

for port in mido.get_input_names():
    if port[:len(midiname)]==midiname:
        print("Using '%s' for MMC input" % port)
        inport = mido.open_input(port)

if not inport:
    sys.exit("Unable to open MIDI inport")


# Start AbletonLink and register call back

link = LinkToPy.LinkInterface("C:\\User\\simon\\Downloads\\Carabiner_Win_x64_v1.1.6\\Carabiner.exe")
link.status(callback_status)

link.enable_start_stop_sync()

while True:
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            if msg.data == (0x7f, 0x7f, 0x06, 0x03):
                # MMC Play
                if playing == False:
                    monotonic_us = int(time.monotonic() * 1000000)
                    print("Play: %d us (ghost time)" % (monotonic_us + delta_us))
                    link.start_playing(monotonic_us + delta_us)

            if msg.data == (0x7f, 0x7f, 0x06, 0x01):
                # MMC Stop
                if playing == True:
                    monotonic_us = int(time.monotonic() * 1000000)
                    print("Stop: %d us (ghost time)" % (monotonic_us + delta_us))
                    link.stop_playing(monotonic_us + delta_us)

