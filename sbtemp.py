#!/usr/bin/env python3

import os
import asyncio
import logging
import requests
from hashlib import sha256
import hmac
from base64 import b64encode
from time import sleep, time, strftime, localtime
from kasa import SmartPlug
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

# --- To be passed in to container ---
# Required Vars
PLUG_IP = os.getenv('PLUG_IP')
DAY_LOW = int(os.getenv('DAY_LOW', 65))
DAY_HIGH = int(os.getenv('DAY_HIGH', 69))
NIGHT_LOW = int(os.getenv('NIGHT_LOW', 62))
NIGHT_HIGH = int(os.getenv('NIGHT_HIGH', 66))
NIGHT_BEGIN = os.getenv('NIGHT_BEGIN')
NIGHT_END = os.getenv('NIGHT_END')
SLEEP_TIME = int(os.getenv('SLEEP_TIME', 300))
TOKEN = os.getenv('TOKEN')
SECRET = os.getenv('SECRET')
DEVID = os.getenv('DEVID')
INFLUX_BUCKET = os.getenv('INFLUX_BUCKET')
INFLUX_ORG = os.getenv('INFLUX_ORG')
INFLUX_TOKEN = os.getenv('INFLUX_TOKEN')
INFLUX_URL = os.getenv('INFLUX_URL')
INFLUX_MEASUREMENT = os.getenv('INFLUX_MEASUREMENT')

# Optional Vars
DEBUG = int(os.getenv('DEBUG', 0))

# --- Other Globals ---
VER = '2.6'
UA_STRING = f"sbtemp.py/{VER}"
URL = 'https://api.switch-bot.com/v1.1/devices/{}/status'

# Setup logger
logger = logging.getLogger()
ch = logging.StreamHandler()
if DEBUG:
    logger.setLevel(logging.DEBUG)
    ch.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)
    ch.setLevel(logging.INFO)

formatter = logging.Formatter('[%(levelname)s] %(asctime)s %(message)s',
                              datefmt='[%d %b %Y %H:%M:%S %Z]')
ch.setFormatter(formatter)
logger.addHandler(ch)


def c2f(celsius: float) -> float:
    return (celsius * 9/5) + 32


def build_headers(secret: str, token: str) -> dict:
    nonce = ''
    t = int(round(time() * 1000))
    string_to_sign = f'{token}{t}{nonce}'
    b_string_to_sign = bytes(string_to_sign, 'utf-8')
    b_secret = bytes(secret, 'utf-8')
    sign = b64encode(hmac.new(b_secret, msg=b_string_to_sign,
                              digestmod=sha256).digest())
    headers = {
        'Authorization': token,
        't': str(t),
        'sign': sign,
        'nonce': nonce
    }
    return headers


def build_url(url_template: str, devid: str) -> str:
    return url_template.format(devid)


def read_sensor(devid: str, secret: str, token: str) -> list:
    url = build_url(URL, devid)
    headers = build_headers(secret, token)
    r = requests.get(url, headers=headers)
    return [round(c2f(r.json()['body']['temperature']), 1),
            r.json()['body']['humidity']]


def check_time_range(time: str, time_range: list) -> bool:
    if time_range[1] < time_range[0]:
        return time >= time_range[0] or time <= time_range[1]
    return time_range[0] <= time <= time_range[1]


async def plug_off(ip: str) -> None:
    p = SmartPlug(ip)
    await p.update()
    await p.turn_off()


async def plug_on(ip: str) -> None:
    p = SmartPlug(ip)
    await p.update()
    await p.turn_on()


async def read_consumption(ip: str) -> float:
    p = SmartPlug(ip)
    await p.update()
    watts = await p.current_consumption()
    return watts


def main() -> None:
    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN,
                                   org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
    time_range = (NIGHT_BEGIN, NIGHT_END)
    logger.info(f"Startup: {UA_STRING}")
    while True:
        (deg_f, rel_hum) = read_sensor(DEVID, SECRET, TOKEN)
        watts = asyncio.run(read_consumption(PLUG_IP))
        record = [
            {
                "measurement": INFLUX_MEASUREMENT,
                "fields": {
                    "degF": deg_f,
                    "rH": rel_hum,
                    "power": watts
                }
            }
        ]
        write_api.write(bucket=INFLUX_BUCKET, record=record)
        now = strftime("%H:%M", localtime())
        if check_time_range(now, time_range):
            # We are in night schedule
            if deg_f < NIGHT_LOW:
                asyncio.run(plug_on(PLUG_IP))
                logger.info(f"Night: Change state to ON, temp: {deg_f}")
            elif deg_f > NIGHT_HIGH:
                asyncio.run(plug_off(PLUG_IP))
                logger.info(f"Night: Change state to OFF, temp: {deg_f}")
            else:
                # no state change required
                pass
        else:
            # we are in day schedule
            if deg_f < DAY_LOW:
                asyncio.run(plug_on(PLUG_IP))
                logger.info(f"Day: Change state to ON, temp: {deg_f}")
            elif deg_f > DAY_HIGH:
                asyncio.run(plug_off(PLUG_IP))
                logger.info(f"Day: Change state to OFF, temp: {deg_f}")
            else:
                # no state change required
                pass
        sleep(SLEEP_TIME)


if __name__ == "__main__":
    main()
