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


def centered_text(draw=None, msg='', y=0, font=None, fill='black'):
    ''' Draw text centered on the display at the given Y '''
    W, H = draw.im.size
    w, h = draw.textsize(msg, font=font)
    draw.text(((W-w)/2, y), msg, font=font, fill=fill)


def right_text(draw=None, msg='', y=0, font=None, fill='black'):
    ''' Draw text centered in the right col of the display at the given Y '''
    W, H = draw.im.size
    w, h = draw.textsize(msg, font=font)
    draw.text((W-w-5, y), msg, font=font, fill=fill)


def horizontal_line(draw=None, y=0, fill='black'):
    ''' Draw a horizontal line at the given Y '''
    W, H = draw.im.size
    draw.line((0, y, W, y), fill=fill)


def data_line(draw=None, y=0, label=None, value=None, font=None, fill='black'):
    draw.text((5, y), label, font=font, fill=fill)
    right_text(draw=draw, msg=value, y=y, font=font)
    horizontal_line(draw=draw, y=y+20, fill=fill)


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
pv_power_1h = get_average(client=client, field=PV_POWER_FIELD, duration='60m')

pv_kwh_avg = get_average(
    client=client, field=PV_POWER_FIELD, duration=f'{minutes_since_midnight}m')
pv_wh = pv_kwh_avg * (minutes_since_midnight / 60)
pv_ah = pv_wh / 12

battery_flow_1h = get_average(
    client=client, field=BATTERY_FLOW_FIELD, duration='60m')

# If we got a zero reading on the SOC, just bail out.  A hack we will circle
# back around to later to fix properly.
if not battery_soc:
    exit()

if pv_power < 0:
    pv_power = 0

# Calculate some values we want to display
battery_load = pv_power - battery_flow
battery_load_1h = pv_power_1h - battery_flow_1h

time_to_empty = (BATTERY_CAPACITY * battery_soc / 100) / battery_flow_1h

# If the remaining time is negative, it means there is a remaining time,
# if it is positive then it means we are not currently draining the battery.

if time_to_empty < 0:
    time_to_empty = round(-time_to_empty)
else:
    time_to_empty = '\u221e'  # infinity symbol

try:
    # Initialize the e-ink Display and associated data structures
    epd = epd2in7.EPD()
    epd.init()

    image = Image.new('1', (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)

    font = ImageFont.truetype('monaco.dfont', 17)

    if battery_flow > 0:
        battery_state = 'Charging'
    else:
        battery_state = 'Discharging'

    image = Image.new('1', (264, 176), 255)
    draw = ImageDraw.Draw(image)

    h, w = draw.textsize(f'{battery_soc}%', font=font)
    draw.text((45-h, 5), f'{battery_soc}%', font=font, fill='black')
    draw.rectangle((50, 5, 259, 25), outline='black', fill='white')
    draw.rectangle((53, 8, battery_soc/100*264-8, 22), fill='black')

    draw.text((12, 30), f'Solar Power  {pv_power:>3} Watts', font=font, fill='black')
    draw.text((12, 54), f'  Generated  {round(pv_ah):>3} Amp Hrs', font=font, fill='black')
    draw.text((12, 78), f' Power Draw  {battery_load:>3} Watts', font=font, fill='black')

    draw.text((12, 102), f' Batt State  {battery_state}', font=font, fill='black')
    draw.text((12, 126), f'  Remaining  {time_to_empty:>3} Hours', font=font, fill='black')
    draw.text((12, 150), f'Last Update  {now.strftime("%m/%d %H:%M")}', font=font, fill='black')

    draw.line((132, 30, 132, 176), fill='black')
    draw.line((10, 52, 254, 52), fill='black')
    draw.line((10, 76, 254, 76), fill='black')
    draw.line((10, 100, 254, 100), fill='black')
    draw.line((10, 124, 254, 124), fill='black')
    draw.line((10, 148, 254, 148), fill='black')

    epd.display(epd.getbuffer(image))
    epd.sleep()

except IOError as e:
    logging.info(e)

except KeyboardInterrupt:
    logging.info("ctrl + c:")
    epd2in7.epdconfig.module_exit()

