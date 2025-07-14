from dotenv import load_dotenv
import requests
import datetime
import os
import time
import serial

#Serial communication
SERIAL_PORT = '/dev/tty.usbmodem1103'
BAUDRATE = 9600

# Load .env and API key
load_dotenv()
FLIGHTAWARE_KEY = os.getenv("FLIGHTAWARE_KEY")
FLIGHTAWARE_URL = "https://aeroapi.flightaware.com/aeroapi"

# Configuration
AIRPORT_ICAO = "KORD"
RUNWAY_NUMBER = "28R"
FETCH_INT = 10  # seconds

departures = {}
arrivals = {}
departed = []
arrived = []

def date_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)

def update_departures(airport_icao, duration_sec=60*2):
    start_date = date_now() - datetime.timedelta(seconds=duration_sec)
    end_date = date_now()

    headers = {
        "Accept": "application/json",
        "x-apikey": FLIGHTAWARE_KEY
    }
    params = {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
    }
    url = f"{FLIGHTAWARE_URL}/airports/{airport_icao}/flights/departures"

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        for flight in data.get("departures", []):
            if flight.get("actual_runway_off") == RUNWAY_NUMBER:
                if flight["ident"] not in departed:
                    departures[flight["ident"]] = {
                        "type": "departure",
                        "ident": flight["ident"],
                        "time": flight.get("estimated_out")
                    }
    else:
        print(f"Error fetching departures: {response.status_code} - {response.text}")

def update_arrivals(airport_icao, duration_sec=60*2):
    start_date = date_now() - datetime.timedelta(seconds=duration_sec)
    end_date = date_now()

    headers = {
        "Accept": "application/json",
        "x-apikey": FLIGHTAWARE_KEY
    }
    params = {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
    }
    url = f"{FLIGHTAWARE_URL}/airports/{airport_icao}/flights/arrivals"

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        for flight in data.get("arrivals", []):
            if flight.get("actual_runway_on") == RUNWAY_NUMBER:
                if flight["ident"] not in arrived:
                    arrivals[flight["ident"]] = {
                        "type": "arrival",
                        "ident": flight["ident"],
                        "time": flight.get("estimated_on")
                    }
    else:
        print(f"Error fetching arrivals: {response.status_code} - {response.text}")

# Initial fetch
update_departures(AIRPORT_ICAO)
update_arrivals(AIRPORT_ICAO)
print("Departures updated:", departures)
print("Arrivals updated:", arrivals)

i = 0
while True:
    # try:
    update_departures(AIRPORT_ICAO)
    update_arrivals(AIRPORT_ICAO)
    
    with serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1) as ser:
        time.sleep(2)  # Give XIAO time to initialize
        if len(list(departures.keys())) > 0:
            msg = "DEPARTURE"
            print("Sending departure message for flight:", list(departures.keys())[0])
            departed.append(list(departures.keys())[0])
            del departures[list(departures.keys())[0]]
        elif len(list(arrivals.keys())) > 0:
            msg = "ARRIVAL"
            print("Sending arrival message for flight:", list(arrivals.keys())[0])
            arrived.append(list(arrivals.keys())[0])
            del arrivals[list(arrivals.keys())[0]]
        else:
            msg = "NOFLIGHT"
        ser.write((msg + "\n").encode())
        print("Sent:", msg.strip())
    
    print(f"[{i}] Departures:", departures)
    print(f"[{i}] Arrivals:", arrivals)
    # except Exception as e:
    #     print(f"An error occurred: {e}")
    time.sleep(FETCH_INT)
    i += 1
