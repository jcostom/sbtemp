#!/usr/bin/python3

import os
import json
import time
import asyncio
import requests
from kasa import SmartPlug
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

plugIP = os.getenv('plugIP')
dayLow = int(os.getenv('dayLow', 65))
dayHigh = int(os.getenv('dayHigh',69))
nightLow = int(os.getenv('nightLow', 62))
nightHigh = int(os.getenv('nightHigh',66))
sleepTime = int(os.getenv('sleepTime', 300))
nightBegin = os.getenv('nightBegin')
nightEnd = os.getenv('nightEnd')
APIKEY = os.getenv('APIKEY')
DEVID = os.getenv('DEVID')
influxBucket = os.getenv('influxBucket')
influxOrg = os.getenv('influxOrg')
influxToken = os.getenv('influxToken')
influxURL = os.getenv('influxURL')
influxMeasurement = os.getenv('influxMeasurement')

def c2f(celsius):
    return (celsius * 9/5) + 32

def readSensor(sbURL, sbHeaders):
    r = requests.get(sbURL, headers=sbHeaders)
    # return array of (degF, rHum)
    return (round(c2f(r.json()['body']['temperature']),1), r.json()['body']['humidity'])

def writeLogEntry(message, status):
    print(time.strftime("[%d %b %Y %H:%M:%S %Z]", time.localtime()) + " {}: {}".format(message, status))

def checkTimeRange(time, timeRange):
    if timeRange[1] < timeRange[0]:
        return time >= timeRange[0] or time <= timeRange[1]
    return timeRange[0] <= time <= timeRange[1]

async def plugOff(ip):
    p = SmartPlug(ip)
    await p.update()
    await p.turn_off()

async def plugOn(ip):
    p = SmartPlug(ip)
    await p.update()
    await p.turn_on()

async def readConsumption(ip):
    p = SmartPlug(ip)
    await p.update()
    watts = await p.current_consumption()
    return(watts)

def main():
    url = "/".join(
        ("https://api.switch-bot.com/v1.0/devices",
        DEVID,
        "status")
    )
    headers = { 'Authorization': APIKEY }
    influxClient = InfluxDBClient(url=influxURL,token=influxToken,org=influxOrg)
    write_api = influxClient.write_api(write_options=SYNCHRONOUS)
    timeRange = (nightBegin, nightEnd)
    writeLogEntry('Startup','')
    while True:
        (degF, rH) = readSensor(url, headers)
        watts = asyncio.run(readConsumption(plugIP))
        record = [
            {
                "measurement": influxMeasurement,
                "fields": {
                    "degF": degF,
                    "rH": rH,
                    "power": watts
                }
            }
        ]
        write_api.write(bucket=influxBucket, record=record)
        now = time.strftime("%H:%M", time.localtime())
        if checkTimeRange(now, timeRange):
            # We are in night schedule
            if degF < nightLow:
                asyncio.run(plugOn(plugIP))
                writeLogEntry('Night: Change state to ON, temp', degF)
            elif degF > nightHigh:
                asyncio.run(plugOff(plugIP))
                writeLogEntry('Night: Change state to OFF, temp', degF)
            else:
                # no state change required
                pass
        else:
            # we are in day schedule
            if degF < dayLow:
                asyncio.run(plugOn(plugIP))
                writeLogEntry('Day: Change state to ON, temp', degF)
            elif degF > dayHigh:
                asyncio.run(plugOff(plugIP))
                writeLogEntry('Day: Change state to OFF, temp', degF)
            else:
                # no state change required
                pass
        time.sleep(sleepTime)

if __name__ == "__main__":
    main()
