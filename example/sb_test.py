import asyncio
from bleak import BleakClient

import sys
import time
import binascii
import threading

address = "5f:0e:da:ae:84:86"

SB_PULSE_V2_SERVICE_UUID = "ccb2986e-1b2d-4c29-9cf8-25cdf8fe44fc"
SB_PULSE_V2_CHAR1_UUID =   "15a08173-ac6b-4804-853a-7af4d795a8ad" # NOTIFY
SB_PULSE_V2_CHAR2_UUID =   "fbaf40a5-ccd9-4e41-88f6-ef56c0ba299d" # NORESPONSE

ready = threading.Event()
resp = None

def callback(sender: int, data: bytearray):
    global resp
    us = time.monotonic()

    if data[1] == 0x00 and data[2] == 0x2f:
        # seems to be ticks since 'start'
        timestamp = int.from_bytes(data[3:], "big")
        print("Timestamp: %d @ %f" % (timestamp, us))

        # do some math to work this out....
        resp = b"\x01\x00\x5f\x11\x22\x33\x44"
        #ready.set()


async def main(address):
    global client
    async with BleakClient(address) as client:
        # 'start', and toggle/change tempo
        await client.write_gatt_char(SB_PULSE_V2_CHAR2_UUID, b"\x01\x00\x01\x01")

        # set a number of different tempos
        for i in range(5):
            # 90 BPM = 4228758432 ?
            await client.write_gatt_char(SB_PULSE_V2_CHAR2_UUID, b"\x01\x00\x02\xa0\xbb\x0d\xfc\x00")
            time.sleep(5)

            # 110 BPM = 4228958432 ?
            await client.write_gatt_char(SB_PULSE_V2_CHAR2_UUID, b"\x01\x00\x02\xe0\xc8\x10\xfc\x00")
            time.sleep(5)

        '''
        # request timestamp, reply in notify??
        await client.start_notify(SB_PULSE_V2_CHAR1_UUID, callback)
        for i in range(50):
            ready.clear()
            await client.write_gatt_char(SB_PULSE_V2_CHAR2_UUID, b"\x01\x00\x2f")
            ready.wait(timeout=0.5)
            if ready.isSet():
                # send response
                await client.write_gatt_char(SB_PULSE_V2_CHAR2_UUID, resp)

        asyncio.sleep(5)
        await client.stop_notify(SB_PULSE_V2_CHAR1_UUID)
        '''

        # 'stop'
        await client.write_gatt_char(SB_PULSE_V2_CHAR2_UUID, b"\x01\x00\x01\x00")


if sys.version_info >= (3, 7):
    asyncio.run(main(address))
else:
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(address))
