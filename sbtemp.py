#!/usr/bin/env python3

import os
import asyncio
import logging
import requests
import secrets
from hashlib import sha256
import hmac
from base64 import b64encode
import time
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
PRESENCE_TIMEOUT = int(os.getenv('PRESENCE_TIMEOUT', 1800))
PRESENCE_CHECK_INTERVAL = int(os.getenv('PRESENCE_CHECK_INTERVAL', 30))
TEMP_READ_INTERVAL = int(os.getenv('TEMP_READ_INTERVAL', 300))
TOKEN = os.getenv('TOKEN')
SECRET = os.getenv('SECRET')
SENSOR = os.getenv('SENSOR')
MOTION_UP = os.getenv('MOTION_UP')
MOTION_DOWN = os.getenv('MOTION_DOWN')
INFLUX_BUCKET = os.getenv('INFLUX_BUCKET')
INFLUX_ORG = os.getenv('INFLUX_ORG')
INFLUX_TOKEN = os.getenv('INFLUX_TOKEN')
INFLUX_URL = os.getenv('INFLUX_URL')
INFLUX_MEASUREMENT = os.getenv('INFLUX_MEASUREMENT')

# Optional Vars
DEBUG = int(os.getenv('DEBUG', 0))

# --- Other Globals ---
VER = '3.1.2'
UA_STRING = f"sbtemp.py/{VER}"
URL = 'https://api.switch-bot.com/v1.1/devices/{}/status'

# Setup logger
LOG_LEVEL = 'DEBUG' if DEBUG else 'INFO'
logging.basicConfig(level=LOG_LEVEL,
                    format='[%(levelname)s] %(asctime)s %(message)s',
                    datefmt='[%d %b %Y %H:%M:%S %Z]')
logger = logging.getLogger()


def c2f(celsius: float) -> float:
    return (celsius * 9/5) + 32


def build_headers(secret: str, token: str) -> dict:
    nonce = secrets.token_urlsafe()
    t = int(round(time.time() * 1000))
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


def read_motion(devid: str, secret: str, token: str) -> bool:
    url = build_url(URL, devid)
    headers = build_headers(secret, token)
    r = requests.get(url, headers=headers)
    return r.json()['body']['moveDetected']


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
    logger.info(f"Startup: {UA_STRING}")
    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN,
                                   org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
    time_range = (NIGHT_BEGIN, NIGHT_END)
    # init motion last-seen as right now
    # since Switchbot doesn't keep a history
    motion_last_seen = int(time.mktime(time.localtime()))
    # figure out how many times we need to check per cycle
    num_presence_checks = int(TEMP_READ_INTERVAL / PRESENCE_CHECK_INTERVAL)
    # If num_presence_checks has a remainder, add one to the checks total
    if TEMP_READ_INTERVAL % PRESENCE_CHECK_INTERVAL > 0:
        logger.debug("Found remainder in calculating num_presence_checks, adding 1 to check count.")  # noqa E501
        num_presence_checks += 1
    else:
        logger.debug("No remainder found, leaving num_presence_checks count as-is.")  # noqa E501

    # Initialize HOME_STATUS as home
    HOME_STATUS = 'home'

    while True:
        (deg_f, rel_hum) = read_sensor(SENSOR, SECRET, TOKEN)
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

        # Do presence check cycle
        for i in range(1, num_presence_checks):
            up_status = read_motion(MOTION_UP, SECRET, TOKEN)
            logger.debug(f"Motion Sensor {MOTION_UP} shows {up_status}.")
            down_status = read_motion(MOTION_DOWN, SECRET, TOKEN)
            logger.debug(f"Motion Sensor {MOTION_DOWN} shows {down_status}.")
            if up_status or down_status:
                logger.debug("Motion Detected! Updating last seen value.")
                motion_last_seen = int(time.mktime(time.localtime()))
            else:
                logger.debug("No motion detected. No update to last seen value.")  # noqa E501
            time.sleep(PRESENCE_CHECK_INTERVAL)

        # Check to see if we've hit the Presence Timeout value and act.
        t_now = int(time.mktime(time.localtime()))
        if t_now - motion_last_seen >= PRESENCE_TIMEOUT:
            # House is empty, so turn off
            if HOME_STATUS == 'home':
                HOME_STATUS = 'away'
                logger.info(f"House shows empty, setting status to {HOME_STATUS}")  # noqa E501
                asyncio.run(plug_off(PLUG_IP))
        else:
            # House is occupied, so check schedule, temp ranges, etc.
            if HOME_STATUS == 'away':
                HOME_STATUS = 'home'
                logger.info(f"House shows occupied, setting status to {HOME_STATUS}")  # noqa E501
            now = time.strftime("%H:%M", time.localtime())
            if check_time_range(now, time_range):
                # We are in night schedule
                if deg_f < NIGHT_LOW:
                    asyncio.run(plug_on(PLUG_IP))
                    logger.info(f"Night: Change state to ON, temp: {deg_f}")  # noqa E501
                elif deg_f > NIGHT_HIGH:
                    asyncio.run(plug_off(PLUG_IP))
                    logger.info(f"Night: Change state to OFF, temp: {deg_f}")  # noqa E501
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


if __name__ == "__main__":
    main()
