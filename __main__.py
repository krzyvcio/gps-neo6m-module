import re
import serial
import threading
import sqlite3
import time
import datetime
import os
import requests

# Color constants
RESET = '\033[0m'
BLUE = '\033[94m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
RED = '\033[91m'
GRAY = '\033[90m'

dbSchema = '''
CREATE TABLE gps_data (
    time TEXT,
    latitude REAL,
    latitude_dir TEXT,
    longitude REAL,
    longitude_dir TEXT,
    speed REAL,
    course REAL,
    date TEXT
);

CREATE TABLE raw_data (
    raw_data TEXT
);

CREATE TABLE errors (
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

'''

_WACHER_API_TOKEN_ = os.environ.get('WATCHER_API_TOKEN')
_SERIAL_ = '/dev/ttyAMA0'

weather_api = f'https://api.watcher.com/api/v1/streams?token={_WACHER_API_TOKEN_}'

def get_weather_data(lat, lon):
    # https://api.openweathermap.org/data/3.0/onecall?lat=33.44&lon=-94.04&appid={API key}
    if not _WACHER_API_TOKEN_:
        return None
    try:
        response = requests.get(f'{weather_api}&lat={lat}&lon={lon}')
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        print(f'An error occurred while getting the weather data: {e}')
        insert_error(f'An error occurred while getting the weather data: {e}')
        return None




########
current_time = int(time.time())

class GPSData:
    def __init__(self, message, current, total, satellites):
        self.message = message
        self.current = current
        self.total = total
        self.satellites = satellites


    def __str__(self):
        return f'GPS satellites in view, Message {self.message}, {self.current} of {self.total}, {self.satellites} satellites'


def print_gps_data(m, lat_decimal, lon_decimal):
    print(GREEN)
    print(f'Time: {m.group("time")}') 
    print(f'Latitude: {m.group("lat_dir")} {lat_decimal}') 
    print(f'Longitude: {m.group("lon_dir")} {lon_decimal}') 
    print(f'Speed: {m.group("speed")} knots')
    print(f'Course: {m.group("course")} degrees')
    print(f'Date: {m.group("date")}')
    print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    print(RESET)

def print_fix_data(m, lat_decimal, lon_decimal, ):
    print(GREEN)
    print(f'Time: {m.group("time")}') 
    print(f'Latitude: {m.group("lat_dir")} {lat_decimal}') 
    print(f'Longitude: {m.group("lon_dir")} {lon_decimal}') 
    print(f'Fix quality: {m.group("fix")}')
    print(f'Satellites used: {m.group("sats")}') 
    print(f'HDOP: {m.group("hdop")}')
    print(f'Altitude: {m.group("alt")} {m.group("units")}')
    print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    print(RESET)

def insert_gps_data(m, lat_decimal, lon_decimal, line):
    conn = sqlite3.connect('gpsCors.db')
    c = conn.cursor()
    c.execute('''INSERT INTO gps_data (time, latitude, latitude_dir, longitude, longitude_dir, speed, course, date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (m.group("time"), lat_decimal, m.group("lat_dir"), lon_decimal, m.group("lon_dir"), float(m.group("speed")), float(m.group("course")), m.group("date")))
    #insert raw data - line
    c.execute('''INSERT INTO raw_data (raw_data)
                    VALUES (?)''', (line,))
    conn.commit()
    conn.close()

def insert_fix_data(m, lat_decimal, lon_decimal, line):
    conn = sqlite3.connect('gpsCors.db')
    c = conn.cursor()
    c.execute('''INSERT INTO gps_data (time, latitude, latitude_dir, longitude, longitude_dir, fix_quality, satellites_used, hdop, altitude)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (m.group("time"), lat_decimal, m.group("lat_dir"), lon_decimal, m.group("lon_dir"), int(m.group("fix")), int(m.group("sats")), float(m.group("hdop")), f'{m.group("alt")} {m.group("units")}'))
    c.execute('''INSERT INTO raw_data (raw_data)    
                    VALUES (?)''', (line,))
    conn.commit()
    conn.close()

def insert_error(error):
    conn = sqlite3.connect('gpsCors.db')
    c = conn.cursor()
    c.execute('''INSERT INTO errors (error)
                    VALUES (?)''', (error,))
    conn.commit()
    conn.close()

def parse_gps_data(line):
    try:
        if not line:
            return
        line = line.strip()
        if line.startswith('$GNRMC'):

            # Recommended minimum data
            # $GNRMC - Recommended Minimum Navigation Information: This sentence includes the most essential navigational information such as latitude, longitude, speed over ground, course over ground, date, magnetic variation, etc.
            m = re.match(r'\$GNRMC,(?P<time>\d+\.\d+),(?P<status>[AV]),(?P<lat>\d+\.\d+),(?P<lat_dir>[NS]),(?P<lon>\d+\.\d+),(?P<lon_dir>[EW]),(?P<speed>\d+\.\d+),(?P<course>\d+\.\d+),(?P<date>\d+\.\d+)', line)
            if m:
                print(YELLOW)
              
                lat = float(m.group("lat"))
                lat_dir = m.group("lat_dir")
                lon = float(m.group("lon"))
                lon_dir = m.group("lon_dir")
                lat_decimal = lat / 100 if lat_dir == 'N' else -lat / 100
                lon_decimal = lon / 100 if lon_dir == 'E' else -lon / 100
                print_gps_data(m, lat_decimal, lon_decimal )
                print(RESET)

        elif line.startswith('$GNGGA'):
            # Fix data
            # $GNGGA - Global Positioning System Fix Data: This sentence provides information about the quality of the GPS fix. It includes data such as time, latitude, longitude, fix quality, number of satellites being tracked, horizontal dilution of position, altitude above sea level, height of geoid (sea level) above WGS84 ellipsoid, etc.
            m = re.match(r'\$GNGGA,(?P<time>\d+\.\d+),(?P<lat>\d+\.\d+),(?P<lat_dir>[NS]),(?P<lon>\d+\.\d+),(?P<lon_dir>[EW]),(?P<fix>\d+),(?P<sats>\d+),(?P<hdop>.+),(?P<alt>.+),(?P<units>.+),(?P<undulation>.+),(?P<age>.+),(?P<stationID>.+)', line)
            if m:
                print(GREEN)
                lat = float(m.group("lat"))
                lat_dir = m.group("lat_dir")
                lon = float(m.group("lon"))
                lon_dir = m.group("lon_dir")
                lat_decimal = lat / 100 if lat_dir == 'N' else -lat / 100
                lon_decimal = lon / 100 if lon_dir == 'E' else -lon / 100
                print_fix_data(m, lat_decimal, lon_decimal)
                print(RESET)
    except Exception as e:
        print(RED)
        print(f'An error occurred while parsing the GPS data: {e}')
        print(RESET)
        insert_error(f'An error occurred while parsing the GPS data: {e}')



def main():
    line_count = 0
    error_count = 0
  
    while True:
        try:
            epochtime = int(time.time())
            
            with serial.Serial(_SERIAL_, 9600, timeout=1) as ser:
                while True:
                    line = ser.readline()
                    try:
                        line = line.decode()
                    except UnicodeDecodeError:
                        line = line.decode('latin-1')
                    parse_gps_data(line)

                    line_count += 1
                    error_count = 0  # Reset error count if no error occurred

        except serial.SerialException:
            error_count += 1
            print(RED)
            print("SerialException occurred. Attempting to reconnect in 100 milliseconds...")
            print(RESET)
            insert_error("SerialException occurred. Attempting to reconnect in 100 milliseconds...")

            if error_count >= 10:
                print("Max error count reached. Restarting serial connection...")
                ser.close()  # Close the current serial connection
                time.sleep(1)  # Wait for 1 second before reconnecting
                error_count = 0  # Reset error count
                insert_error("Max error count reached. Restarting serial connection...")

if __name__ == "__main__":
    try:
        conn = sqlite3.connect('gpsCors.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS gps_data
                 (time TEXT, latitude REAL, latitude_dir TEXT, longitude REAL, longitude_dir TEXT, fix_quality INTEGER, satellites_used INTEGER, hdop REAL, altitude TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS raw_data
                     (raw_data TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS errors
                        (error TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        

        conn.commit()
        conn.close()

    except sqlite3.Error as e:
        print("An error occurred while creating the table:", e)
        insert_error(f'An error occurred while creating the table: {e}')
    
    while True:
        try:
            main()
        except Exception as e:  # Catch all exceptions
            insert_error(f'An error occurred while running the main function: {e}')
            # //try open same script on new thread
            t = threading.Thread(target=main)
            t.start()
            
            

