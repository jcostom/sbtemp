# sbtemp

## Controlling a Kasa Smart Plug using data from a SwitchBot Meter

This came about from a conversation with a friend. His laundry room doesn't have a heat source and so naturally, with NJ winters, it gets cold. So, this is a container wrapped around a Python script that uses the SwitchBot REST API to read temperature (and relative humidity, because why not - it's there, may as well), looks at day vs night schedules for pre-defined temp ranges, and decides whether or not to activate a small relatively low-power heater connected to the Kasa smart plug.

I know, never connect those to smart plugs. This space heater is small and draws far less power than the plug is rated for. In his case, he's using a Kasa KP115, which is rated for 1800W, which is 15A @ 120V. Given that the most power we've seen this thing suck out of the wall is 560W, we feel pretty safe with it.

For an added bonus and general showing off, we're stuffing the data into InfluxDB and making pretty graphs of temperature, humidity, and power use. What can I say? I'm a data nerd.

To bring this thing online, first setup an InfluxDB instance. I used InfluxDB 2.1, and the code is written for the Influx 2.0 API, so bear that in mind. In other words, don't stand up InfluxDB 1.something and wonder why it's not working. It still runs great, even on InfluxDB 2.6, as of Dec 2022.

Next, fill in the various variables in the docker-compose file for sbtemp and launch the container. You can do it from the CLI, or the way I do, from inside Portainer. You do you.

In case it isn't obvious - if you don't want different night and day temp ranges, just make the values the same. In other words, make nightLow = dayLow and nightHigh = dayHigh.
