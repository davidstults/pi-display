import datetime
import pytz

from influxdb import InfluxDBClient
from waveshare_epd import epd2in7
from PIL import Image,ImageDraw,ImageFont

TIMEZONE = 'US/Pacific'
INFLUX_HOSTNAME = '10.11.12.51'
INFLUX_PORT = 8086
INFLUX_DATABASE = 'venus'
BATTERY_SOC_FIELD = 'battery/Soc'
PV_POWER_FIELD = 'system/Dc/Pv/Power'
BATTERY_FLOW_FIELD = 'battery/Dc/0/Power'
BATTERY_CAPACITY = 1200

def centered_text(draw=None, msg='', y=0, font=None, fill='black'):
    W, H = draw.im.size
    w, h = draw.textsize(msg, font=font)
    draw.text(((W-w)/2, y), msg, font=font, fill=fill)

def left_centered_text(draw=None, msg='', y=0, font=None, fill='black'):
    W, H = draw.im.size
    w, h = draw.textsize(msg, font=font)
    draw.text(((W/2-w)/2, y), msg, font=font, fill=fill)

def right_centered_text(draw=None, msg='', y=0, font=None, fill='black'):
    W, H = draw.im.size
    w, h = draw.textsize(msg, font=font)
    draw.text((W/2+(W/2-w)/2, y), msg, font=font, fill=fill)

def horizontal_line(draw=None, y=0, fill='black'):
    W, H = draw.im.size
    draw.line((0, y, W, y), fill=fill)

def get_1m_average(client=None, field=None):
    try:
        query = f'SELECT mean("value") FROM "{field}" WHERE time >= now() - 1m'
        result = list(client.query(query, database=INFLUX_DATABASE)[(field, None)])[0]['mean']
        return round(result)
    except IndexError:
        return 0

now = datetime.datetime.now(tz=pytz.timezone('US/Eastern')).strftime('%m/%d/%Y %I:%M%p').lstrip("0").replace(" 0", " ").lower()

client = InfluxDBClient(INFLUX_HOSTNAME, INFLUX_PORT)

battery_soc = get_1m_average(client=client, field=BATTERY_SOC_FIELD)
pv_power = get_1m_average(client=client, field=PV_POWER_FIELD)
battery_flow = get_1m_average(client=client, field=BATTERY_FLOW_FIELD)
battery_load = pv_power - battery_flow

time_to_empty = (BATTERY_CAPACITY * battery_soc / 100) / battery_flow
print('capacity', BATTERY_CAPACITY, 'soc', battery_soc, 'remain', BATTERY_CAPACITY * battery_soc / 100,'flow', battery_flow, 'tte', time_to_empty)
if time_to_empty < 0:
    time_to_empty = -time_to_empty
    tte_days = datetime.timedelta(hours=time_to_empty).days
    tte_seconds = datetime.timedelta(hours=time_to_empty).seconds
    tte_hours = tte_seconds // 3600
    tte_minutes = tte_seconds % 3600 // 60

    print('time_to_empty seconds', tte_seconds)
    if tte_days:
        print('time_to_empty', f'{tte_days}d {tte_hours}h')
        time_to_empty = f'{tte_days}d'
    else:
        print('time_to_empty', f'{tte_hours}h')
        time_to_empty = f'{tte_hours}h'
else:
    time_to_empty = '∞'

try:
    epd = epd2in7.EPD()
    
    epd.init()
    label_font = ImageFont.truetype('cascadia.otf', 18)
    value_font = ImageFont.truetype('cascadia.otf', 70)
    sub_value_font = ImageFont.truetype('cascadia.otf', 25)
    ts_font = ImageFont.truetype('cascadia.otf', 14)

    image = Image.new('1', (epd.width, epd.height), 255)
    draw = ImageDraw.Draw(image)

    centered_text(draw=draw, msg=f'{battery_soc}%', y=0, font=value_font)
    horizontal_line(draw=draw, y=80)
    left_centered_text(draw=draw, msg=f'PV', y=90, font=label_font)
    right_centered_text(draw=draw, msg=f'FLOW', y=90, font=label_font)
    left_centered_text(draw=draw, msg=f'{pv_power}w', y=118, font=sub_value_font)
    right_centered_text(draw=draw, msg=f'{battery_flow}w', y=118, font=sub_value_font)
    horizontal_line(draw=draw, y=162)
    left_centered_text(draw=draw, msg=f'LOAD', y=172, font=label_font)
    right_centered_text(draw=draw, msg=f'REMAIN', y=172, font=label_font)
    left_centered_text(draw=draw, msg=f'{battery_load}w', y=200, font=sub_value_font)
    right_centered_text(draw=draw, msg=time_to_empty, y=200, font=sub_value_font)
    horizontal_line(draw=draw, y=244)
    centered_text(draw=draw, msg=now, y=246, font=ts_font)
    W, H = draw.im.size
    draw.line((W/2, 80, W/2, 244), fill='black')

    image = image.rotate(270, expand=True)
    epd.display(epd.getbuffer(image))
    epd.sleep()
        
except IOError as e:
    logging.info(e)
    
except KeyboardInterrupt:    
    logging.info("ctrl + c:")
    epd2in7.epdconfig.module_exit()
    exit()
