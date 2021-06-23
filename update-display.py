#!/usr/bin/env python3

import datetime
import logging
import pytz

from influxdb import InfluxDBClient
from waveshare_epd import epd2in7
from PIL import Image, ImageDraw, ImageFont

TIMEZONE = 'US/Pacific'
INFLUX_HOSTNAME = '10.11.12.51'
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


def get_average(client=None, field=None, duration='1m'):
    try:
        query = ('SELECT mean("value") FROM "{field}" '
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
# Format it for display
# now = now.strftime('%m/%d/%Y %I:%M%p').lstrip("0").replace(" 0", " ").lower()
now = now.strftime('%H:%M')

# Grab data out of InfluxDB
client = InfluxDBClient(INFLUX_HOSTNAME, INFLUX_PORT)
battery_soc = get_average(client=client, field=BATTERY_SOC_FIELD)
pv_power = get_average(client=client, field=PV_POWER_FIELD)
battery_flow = get_average(client=client, field=BATTERY_FLOW_FIELD)

pv_power_1h = get_average(client=client, field=PV_POWER_FIELD, duration='60m')
battery_flow_1h = get_average(
    client=client, field=BATTERY_FLOW_FIELD, duration='60m')

# If we got a zero reading on the SOC, just bail out.  A hack we will circle
# back around to later to fix properly.
if not battery_soc:
    exit()

# Calculate some values we want to display
battery_load = pv_power - battery_flow
battery_load_1h = pv_power_1h - battery_flow_1h

time_to_empty = (BATTERY_CAPACITY * battery_soc / 100) / battery_flow_1h

# If the remaining time is negative, it means there is a remaining time,
# if it is positive then it means we are not currently draining the battery.

if time_to_empty < 0:
    time_to_empty = -time_to_empty
    tte_days = datetime.timedelta(hours=time_to_empty).days
    tte_seconds = datetime.timedelta(hours=time_to_empty).seconds
    tte_hours = tte_seconds // 3600
    tte_minutes = tte_seconds % 3600 // 60

    # If our remaining time is on the order of days, we just show
    # the number of days.  If it's less than a day, we show hours.
    if tte_days:
        time_to_empty = f'{tte_days}d'
    else:
        time_to_empty = f'{tte_hours}h'
else:
    time_to_empty = '\u221e'  # infinity symbol

try:
    label_font = ImageFont.truetype('cascadia.otf', 18)
    value_font = ImageFont.truetype('cascadia.otf', 70)
    sub_value_font = ImageFont.truetype('cascadia.otf', 25)
    ts_font = ImageFont.truetype('cascadia.otf', 16)

    # Initialize the e-ink Display and associated data structures
    epd = epd2in7.EPD()
    epd.init()

    # Note: the width/height are swapped here because we will rotate
    # the image from landscape to portrait when we are finished
    # drawing text
    image = Image.new('1', (epd.width, epd.height), 255)
    draw = ImageDraw.Draw(image)

    # The star of this show is the battery state-of-charge.  Make it big.
    centered_text(draw=draw, msg=f'{battery_soc}%', y=0, font=value_font)
    horizontal_line(draw=draw, y=80)

    # Then we have a few supporting fields rendered in smaller fonts,
    data_line(draw=draw, y=80, label='Power', value=f'{pv_power}w',
              font=label_font)
    data_line(draw=draw, y=100, label='Batt Flow', value=f'{battery_flow}w',
              font=label_font)
    data_line(draw=draw, y=120, label='1m Load', value=f'{battery_load}w',
              font=label_font)
    data_line(draw=draw, y=140, label='1h Load', value=f'{battery_load_1h}w',
              font=label_font)
    data_line(draw=draw, y=160, label='Time Left', value=time_to_empty,
              font=label_font)

    horizontal_line(draw=draw, y=244, fill='black')
    data_line(draw=draw, y=244, label='Last Updated', value=now, font=ts_font)

    # The default orientation of the e-ink display is landscape.  We
    # want to orient the RPi upside down and in portrait mode to make
    # cord orientation sensible.  So we rotate our image to match.
    image = image.rotate(270, expand=True)
    epd.display(epd.getbuffer(image))

    # Then we sleep the display so consumption goes to 0
    epd.sleep()

except IOError as e:
    logging.info(e)

except KeyboardInterrupt:
    logging.info("ctrl + c:")
    epd2in7.epdconfig.module_exit()
