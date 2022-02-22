# sample script to toggle/change the tempo of an AbletonLink Session
# in time with the downbeat, intended to work with SoundBrenner watch
#
# uses Link-to-Py & Carabiner:
# https://github.com/bdyetton/LinkToPy
# https://github.com/Deep-Symmetry/carabiner

import LinkToPy
import sched, time
import threading
import signal
import sys

playing = None
prev_bpm = None

time_at_beat = None
beat_at_time = None

event_status = None
event_time_at_beat = None
event_beat_at_time = None

s = None
link = None
mutex_link = None

delta_us = None
deltas = []
deltasum = 0

options = None

tempo_beat = None
tempo_index = 0
tempos = [90, 110]

# ---------------------------------------------

def time_to_ghost(now):
    return int((now * 1000000) + delta_us)

def ghost_to_time(ghost):
    return ((ghost - delta_us) / 1000000)


def callback_status(cb):
    global delta_us, deltas, deltasum
    global playing, prev_bpm

    monotonic_us = int(time.monotonic() * 1000000)

    if prev_bpm != cb['bpm']:
        # changed, therefore we have to reset averaging
        deltas = []
        deltasum = 0
    prev_bpm = cb['bpm']

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

    if not link:
        return

    if not playing:
        #print("Not playing, don't schedule")
        return

    if s:
        event_status.wait(timeout=5)
        if not event_status.isSet():
            print("Huh, status not responding!")
            return

        if not tempo_beat:
            beat = int(link.beat_)
            tempo_beat = beat - (beat % options.quantum)
            tempo_index = 0

        while True:
            new_beat = tempo_beat + options.bar * options.quantum

            # check what 'ghost-time' the new_beat happens
            mutex_link.acquire()
            event_time_at_beat.clear()
            err = link.time_at_beat(new_beat, quantum=options.quantum, \
                    callback=callback_time_at_beat)
            mutex_link.release()

            if not err:
                event_time_at_beat.wait(timeout=0.5)
            if not event_time_at_beat.isSet():
                print("TimeAtBeat slow response!", err)
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

        mutex_link.acquire()
        event_beat_at_time.clear()
        err = link.beat_at_time(time_to_ghost(when), quantum=options.quantum, \
                callback=callback_beat_at_time)
        mutex_link.release()

        if not err:
            event_beat_at_time.wait(timeout=0.5)
        if event_beat_at_time.isSet():
            print("Tempo change scheduled for beat: %f @ %f (now %f)" % \
                    (beat_at_time, time.monotonic(), when))
        else:
            print("BeatAtTime slow response!", err)


def sched_toggle():
    global tempo_index

    if not link:
        return

    if not tempo_beat:
        return

    if options.debug:
        now = time.monotonic()

        mutex_link.acquire()
        event_beat_at_time.clear()
        err = link.beat_at_time(time_to_ghost(now), \
                quantum=options.quantum, \
                callback=callback_beat_at_time)
        mutex_link.release()

        if not err:
            event_beat_at_time.wait(timeout=0.5)

        if event_beat_at_time.isSet():
            print("Tempo set to: %f  (beat: %f @ %f)\n" % \
                    (tempos[tempo_index], beat_at_time, now))
        else:
            print("BeatAtTime slow response!", err)

    mutex_link.acquire()
    link.set_bpm(tempos[tempo_index])

    # mark previous status values as invalid
    event_status.clear()
    mutex_link.release()

    tempo_index = (tempo_index + 1) % len(tempos)
    sched_setup()


def sched_thread():
    global s

    print("Starting scheduler")
    s = sched.scheduler(time.monotonic, time.sleep)

    # auto restart scheduler, should it ever complete all tasks
    while True:
        s.run()
        #print("Scheduler exited")
        time.sleep(0.1)


def signal_handler(signal, frame):
    sys.exit("Terminated by SIGINT")

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
        t = int(parse[i])
        if t >= 20 and t <= 999:
            tempos.append(t)
        else:
            print("Invalid tempo %d (must be 20-999)" % t)
    if not len(tempos):
        sys.exit("No valid tempo specified")

# signal to catch CTRL-C
signal.signal(signal.SIGINT, signal_handler)

# setup scheduler in separate thread
mutex_link = threading.Lock()

event_status = threading.Event()
event_time_at_beat = threading.Event()
event_beat_at_time = threading.Event()

t = threading.Thread(target=sched_thread)
t.daemon = True
t.start()

# Start AbletonLink and register call back
link = LinkToPy.LinkInterface("/home/simon/Carabiner/Carabiner_Linux_x64")
event_status.clear()

mutex_link.acquire()
err = link.status(callback_status)
mutex_link.release()

if not err:
    event_status.wait(timeout=5)
if not event_status.isSet():
    sys.exit("Huh, status not responding", err)

if options.play:
    # force session to start playing
    mutex_link.acquire()
    link.enable_start_stop_sync()
    link.start_playing(time_to_ghost(time.monotonic()))
    mutex_link.release()

while True:
    if playing:
        if not tempo_beat:
            print("Scheduler - Tempos: ", tempos)
            sched_setup()
    else:
        tempo_beat = None

    # keep checking status, so that we can average delta_us
    mutex_link.acquire()
    link.status(callback_status)
    mutex_link.release()

    time.sleep(0.5)

