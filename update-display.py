#!/usr/bin/env python3

import datetime
import logging
import pytz

from influxdb import InfluxDBClient
from waveshare_epd import epd2in7
from PIL import Image, ImageDraw, ImageFont

TIMEZONE = 'US/Pacific'
INFLUX_HOSTNAME = '127.0.0.1'
INFLUX_PORT = 8086
INFLUX_DATABASE = 'venus'
BATTERY_SOC_FIELD = 'battery/Soc'
PV_POWER_FIELD = 'system/Dc/Pv/Power'
BATTERY_FLOW_FIELD = 'battery/Dc/0/Power'
BATTERY_CAPACITY = 1200


def get_average(client=None, field=None, duration='3m'):
    try:
        query = (f'SELECT mean("value") FROM "{field}" '
                 f'WHERE time >= now() - {duration}')

        # query influxdb, which will return a generator
        result = client.query(query, database=INFLUX_DATABASE)

        # pull out the field we want
        result = result[(field, None)]

        # convert to a list, grab the first element, which is a dictionary
        result = list(result)[0]

        # get the value of 'mean', which is what we asked for
        result = result.get('mean', 0)

        # we do not need sub-integer precision
        return round(result)

    except IndexError:
        return 0


def get_yield(client=None, field=PV_POWER_FIELD):
    now = datetime.datetime.now(tz=pytz.timezone(TIMEZONE))
    midnight = datetime.datetime.now(pytz.timezone('US/Pacific')).replace(
        hour=0, minute=0, second=0, microsecond=0)
    minutes_since_midnight = (now - midnight).seconds // 60

    try:
        query = (f'SELECT INTEGRAL("value", 60m) FROM "{field}" '
                 f'WHERE time >= now() - {minutes_since_midnight}m')

        # query influxdb, which will return a generator
        result = client.query(query, database=INFLUX_DATABASE)

        # pull out the field we want
        result = result[(field, None)]

        # convert to a list, grab the first element, which is a dictionary
        result = list(result)[0]

        # get the value of 'integral', which is what we asked for
        result = result.get('integral', 0)

        # we do not need sub-integer precision
        return round(result)

    except IndexError:
        return 0


# Get the local time
now = datetime.datetime.now(tz=pytz.timezone(TIMEZONE))
midnight = datetime.datetime.now(pytz.timezone('US/Pacific')).replace(
    hour=0, minute=0, second=0, microsecond=0)
minutes_since_midnight = (now - midnight).seconds // 60

# Grab data out of InfluxDB
client = InfluxDBClient(INFLUX_HOSTNAME, INFLUX_PORT)
battery_soc = get_average(client=client, field=BATTERY_SOC_FIELD)
pv_power = get_average(client=client, field=PV_POWER_FIELD)
battery_flow = get_average(client=client, field=BATTERY_FLOW_FIELD)
pv_yield = get_yield(client=client)

pv_power_15m = get_average(client=client, field=PV_POWER_FIELD, duration='15m')
battery_flow_15m = get_average(client=client, field=BATTERY_FLOW_FIELD,
                               duration='15m')

# Get average battery in/out flow for last 10 minutes
battery_flow_10m = get_average(
    client=client, field=BATTERY_FLOW_FIELD, duration='10m')

# If we got a zero reading on the SOC, just bail out, we do not have
# any data samples in the last 3 minutes.  This should not often happen
# unless there is a networking problem between the Influx poller and the
# Venus server.

if not battery_soc:
    exit()

# Normalize any negative PV readings to zero.  Not saying those values
# are invalid, but they are usually very small in magnitude and they
# are non-intuitive, so lets exclude them from the display.

if pv_power < 0:
    pv_power = 0

# Calculate how much power is being consumed.  The panel will not generate
# power if it goes nowhere, so it goes to load or to battery.  So we can
# subtract the flow to the battery from the yield from the panel and this
# is our power draw.  We calculate the value for the last 3 minutes to use
# on the display, and the value for the last 15 minutes to use in our
# runtime guesser.

power_draw = pv_power - battery_flow
power_draw_15m = pv_power_15m - battery_flow_15m

# Make a wild ass guess as to how long we could run without any more
# sunlight if we consume the same average power we have been consuming for
# the past 15 minutes.

runtime = (BATTERY_CAPACITY * battery_soc / 100) / power_draw_15m

# If the remaining time is negative, it means there is a remaining time,
# if it is positive then it means we are not currently draining the battery.

if runtime < 0:
    runtime = round(-runtime)
else:
    runtime = '\u221e'  # infinity symbol

try:
    # Initialize the e-ink Display and associated data structures
    epd = epd2in7.EPD()
    epd.init()

    image = Image.new('1', (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)

    font = ImageFont.truetype('monaco.dfont', 17)

    if battery_flow > 0:
        battery_state = 'Charging'
    elif battery_flow < 0:
        battery_state = 'Discharging'
    else:
        battery_state = 'Resting'

    image = Image.new('1', (264, 176), 255)
    draw = ImageDraw.Draw(image)

    h, w = draw.textsize(f'{battery_soc}%', font=font)
    draw.text((45-h, 5), f'{battery_soc}%', font=font, fill='black')
    draw.rectangle((50, 5, 259, 25), outline='black', fill='white')
    draw.rectangle((53, 8, battery_soc/100*264-8, 22), fill='black')

    draw.text((12, 30), f'Solar Power  {pv_power:>3} Watts',
              font=font, fill='black')
    draw.text((12, 54), f'  Generated  {pv_yield:>3} WattHrs',
              font=font, fill='black')
    draw.text((12, 78), f' Power Draw  {power_draw:>3} Watts',
              font=font, fill='black')

    draw.text((12, 102), f' Batt State  {battery_state}',
              font=font, fill='black')
    draw.text((12, 126), f'   Run Time  {runtime:>3} Hours',
              font=font, fill='black')
    draw.text((12, 150), f'Last Update  {now.strftime("%m/%d %H:%M")}',
              font=font, fill='black')

    draw.line((132, 30, 132, 176), fill='black')
    draw.line((10, 52, 254, 52), fill='black')
    draw.line((10, 76, 254, 76), fill='black')
    draw.line((10, 100, 254, 100), fill='black')
    draw.line((10, 124, 254, 124), fill='black')
    draw.line((10, 148, 254, 148), fill='black')

    image = image.rotate(180)
    image.save('output.png')
    epd.display(epd.getbuffer(image))
    epd.sleep()

    with open('output.txt', 'a') as f:
        f.write(f'\n============ {now.strftime("%m/%d %H:%M")} ============\n')
        f.write(f'Battery SOC: {battery_soc}%\n')
        f.write(f'Battery Flow (15m Avg): {battery_flow} Watts ({battery_flow_15m})\n')
        f.write(f'Solar Power (15m Avg): {pv_power} Watts ({pv_power_15m})\n')
        f.write(f'Solar Yield: {pv_yield} Watt Hours\n')
        f.write(f'Power Draw (15m Avg): {power_draw} Watts ({power_draw_15m})\n')
        f.write(f'Battery State: {battery_state}\n')
        f.write(f'Runtime: {runtime} Hours\n')

except IOError as e:
    logging.info(e)

except KeyboardInterrupt:
    logging.info("ctrl + c:")
    epd2in7.epdconfig.module_exit()
