# sample script to toggle/change the tempo of an AbletonLink Session
# in time with the downbeat, intended to work with SoundBrenner watch
#
# uses Link-to-Py & Carabiner:
# https://github.com/bdyetton/LinkToPy
# https://github.com/Deep-Symmetry/carabiner

import LinkToPy
import sched, time
import threading

playing = None
current_bpm = None
current_beat = None

time_at_beat = None
beat_at_time = None

event_status = None
event_time_at_beat = None
event_beat_at_time = None

delta_us = None
deltas = []
deltasum = 0

options = None
link = None
s = None

tempo_beat = None
tempo_index = 0
tempos = [90, 110]  # fails
tempos = [94, 106]  # fails
tempos = [93, 107]  # fails
tempos = [95, 105]  # passes, mostly
tempos = [96, 104]  # passes
tempos = [90, 110]  # fails

# ---------------------------------------------

def time_to_ghost(now):
    return int((now * 1000000) + delta_us)

def ghost_to_time(ghost):
    return ((ghost - delta_us) / 1000000)


def callback_status(cb):
    global delta_us, deltas, deltasum
    global playing, current_bpm, current_beat

    monotonic_us = int(time.monotonic() * 1000000)
 
    if current_bpm != cb['bpm']:
        # changed, therefore we have to reset averaging
        deltas = []
        deltasum = 0

    computed_us = cb['start'] + (1000000 * (cb['beat'] * 60.0 / cb['bpm']))
    delta = computed_us - monotonic_us

    # calculate rolling average
    deltasum += delta
    deltas.append(delta)
    if len(deltas) > 20:
        deltasum -= deltas[0]
        deltas = deltas[1:]

    delta_us = deltasum / len(deltas)

    if 'playing' in cb:
        playing = cb['playing']

    current_bpm = cb['bpm']
    current_beat = cb['beat']
    event_status.set()


def callback_time_at_beat(cb):
    global time_at_beat

    time_at_beat = cb['when']
    event_time_at_beat.set()

def callback_beat_at_time(cb):
    global beat_at_time

    beat_at_time = cb['beat']
    event_beat_at_time.set()

# ---------------------------------------------

def sched_setup():
    global tempo_beat

    if not playing:
        #print("Not playing, don't schedule")
        return

    if s:
        event_status.wait(timeout=5)
        if not event_status.isSet():
            print("Huh, status not responding. Abort!")
            return
        
        if not tempo_beat:
            beat = int(current_beat)
            tempo_beat = beat - (beat % options.quantum)
            tempo_index = 0

        while True:
            new_beat = tempo_beat + options.bar * options.quantum

            # check what 'ghost-time' the new_beat happens
            event_time_at_beat.clear()
            link.time_at_beat(new_beat, quantum=options.quantum, \
                    callback=callback_time_at_beat)

            event_time_at_beat.wait(timeout=1.0)
            if not event_time_at_beat.isSet():
                print("TimeAtBeat slow response!")
                continue

            tempo_beat = new_beat
            when = ghost_to_time(time_at_beat) + (options.milli / 1000)
            now = time.monotonic()

            # far enough in future? otherwise wait for next bar
            if when > now + 0.1:
                break

            #print("waiting for another bar", when, now)

        # Shedule tempo change...
        s.enterabs(when, 1, sched_toggle)

        if not options.debug:
            return

        event_beat_at_time.clear()
        link.beat_at_time(time_to_ghost(when), quantum=options.quantum, \
                callback=callback_beat_at_time)

        event_beat_at_time.wait(timeout=0.5)
        if event_beat_at_time.isSet():
            print("Tempo change scheduled for beat: %f @ %f (now %f)" % \
                    (beat_at_time, time.monotonic(), when))


def sched_toggle():
    global tempo_index

    if not link:
        return

    if not tempo_beat:
        return

    if options.debug:
        event_beat_at_time.clear()
        now = time.monotonic()

        link.beat_at_time(time_to_ghost(now), \
                quantum=options.quantum, \
                callback=callback_beat_at_time)

        event_beat_at_time.wait(timeout=0.5)

        if event_beat_at_time.isSet():
            print("Tempo set to: %f  (beat: %f @ %f)\n" % \
                    (tempos[tempo_index], beat_at_time, now))
        else:
            print("BeatAtTime slow response!")

    link.set_bpm(tempos[tempo_index])

    # mark previous status values as invalid
    event_status.clear()

    tempo_index = (tempo_index + 1) % len(tempos)
    sched_setup()


def sched_thread():
    global s

    print("Starting scheduler")
    s = sched.scheduler(time.monotonic, time.sleep)

    # auto restart scheduler, should it ever complete all tasks
    while True:
        s.run()
        time.sleep(0.1)

# ---------------------------------------------

from argparse import ArgumentParser

parser = ArgumentParser(prog="toggle_bpm")

parser.add_argument("-b", "--bar",
    help="change tempo every BAR bars",
    default=4, type=int, dest="bar")
parser.add_argument("-q", "--quantum",
    help="set QUANTUM, number of beats in bar",
    default=4, type=int, dest="quantum")
parser.add_argument("-t", "--tempos",
    help="an ordered list of tempos, comma separated",
    default="90,110", dest="tempos")

parser.add_argument("-m", "--milli",
    help="delay tempo change by MILLI-seconds",
    default=0.0, type=float, dest="milli")

parser.add_argument("-p", "--play",
    help="automatically start playing",
    action="store_true", dest="play")

parser.add_argument("-d", "--debug",
    help="print out additional debugging",
    action="store_true", dest="debug")

options = parser.parse_args()

if options.tempos:
    tempos = []
    parse = options.tempos.split(',')
    for i in range(len(parse)):
        tempos.append(int(parse[i]))

# setup scheduler in separate thread
t = threading.Thread(target=sched_thread)
t.start()

event_status = threading.Event()
event_time_at_beat = threading.Event()
event_beat_at_time = threading.Event()

# Start AbletonLink and register call back
link = LinkToPy.LinkInterface("/home/simon/Carabiner/Carabiner_Linux_x64")
link.status(callback_status)

time.sleep(1)

if options.play:
    event_status.wait(timeout=5)
    if not event_status.isSet():
        sys.exit("Huh, status not responding")

    # force session to start playing
    link.enable_start_stop_sync()
    link.start_playing(time_to_ghost(time.monotonic()))

while True:
    if playing:
        if not tempo_beat:
            print("Scheduler 1st setup")
            sched_setup()
    else:
        tempo_beat = None

    # keep checking status, so that we can average delta_us
    link.status(callback_status)
    time.sleep(0.1)

