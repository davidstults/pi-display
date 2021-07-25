#!/usr/bin/env python3

import datetime
import logging
import pytz

from influxdb import InfluxDBClient
from PIL import Image, ImageDraw, ImageFont

TIMEZONE = 'US/Pacific'
INFLUX_HOSTNAME = '10.11.12.51'
INFLUX_PORT = 8086
INFLUX_DATABASE = 'venus'
BATTERY_SOC_FIELD = 'battery/Soc'
PV_POWER_FIELD = 'system/Dc/Pv/Power'
BATTERY_FLOW_FIELD = 'battery/Dc/0/Power'
BATTERY_CAPACITY = 1200

UPDATE_DISPLAY = True

if UPDATE_DISPLAY:
    from waveshare_epd import epd2in7


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

runtime = round((BATTERY_CAPACITY * battery_soc / 100) / power_draw_15m)

# If the remaining time is negative, then power draw is negative, which means
# the battery is charging.

if runtime < 0:
    runtime = '\u221e'  # infinity symbol

try:
    if UPDATE_DISPLAY:
        # Initialize the e-ink Display and associated data structures
        epd = epd2in7.EPD()
        epd.init()

    if UPDATE_DISPLAY:
        img_height = epd.height
        img_width = epd.width
    else:
        img_height = 264
        img_width = 176

    image = Image.new('1', (img_height, img_width), 255)
    draw = ImageDraw.Draw(image)

    small_font = ImageFont.truetype('monaco.dfont', 25)
    medium_font = ImageFont.truetype('monaco.dfont', 50)
    big_font = ImageFont.truetype('monaco.dfont', 80)

    if battery_flow > 0:
        battery_state = 'Charging'
    elif battery_flow < 0:
        battery_state = 'Discharging'
    else:
        battery_state = 'Resting'

    image = Image.new('1', (264, 176), 255)
    draw = ImageDraw.Draw(image)

    h, w = draw.textsize(f'{battery_soc}%', font=big_font)
    draw.text(((img_height-h)/2, -10), f'{battery_soc}%',
              font=big_font, fill='black')

    draw.text((5, 143), f'\u2192{pv_power}W',
              font=small_font, fill='black')

    h, w = draw.textsize(f'{power_draw}W\u2192', font=small_font)
    draw.text((img_height-h-5, 143), f'{power_draw}W\u2192',
              font=small_font, fill='black')

    h, w = draw.textsize(f'{pv_yield}Wh', font=small_font)
    draw.text(((img_height-h)/2, 143), f'{pv_yield}Wh',
              font=small_font, fill='black')

    h, w = draw.textsize(f'{runtime} Hours', font=medium_font)
    draw.text(((img_height-h)/2, 81), f'{runtime} Hours',
              font=medium_font, fill='black')

    draw.line((10, 83, 254, 83), fill='black')
    draw.line((10, 84, 254, 84), fill='black')

    draw.line((10, 140, 254, 140), fill='black')
    draw.line((10, 141, 254, 141), fill='black')

    image.save('output.png')

    if UPDATE_DISPLAY:
        # The mounting orientation of the display is upside down
        image = image.rotate(180)

    if UPDATE_DISPLAY:
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
