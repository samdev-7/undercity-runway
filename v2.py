from dotenv import load_dotenv
import requests
import datetime
import os
import time

load_dotenv()

FLIGHTAWARE_KEY = os.getenv("FLIGHTAWARE_KEY")
FLIGHTAWARE_URL = "https://aeroapi.flightaware.com/aeroapi"

AIRPORT_ICAO = "KORD"
RUNWAY_NUMBER = "28R"
FETCH_INT= 10 # seconds

departures = {}
arrivals = {}

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
            # print(f"Processing flight: {flight}")
            if flight["actual_runway_off"] == RUNWAY_NUMBER:
                departures[flight["ident"]] = {
                    type: "departure",
                    "ident": flight["ident"],
                    "time": flight["estimated_out"]
                }
    else:
        print(f"Error fetching departures: {response.status_code} - {response.text}")

update_departures(AIRPORT_ICAO)
print("Departures updated:", departures)

i = 0
while True:
    try:
        update_departures(AIRPORT_ICAO)
        print(f"{i} Departures updated:", list(departures.keys()))
    except Exception as e:
        print(f"An error occurred: {e}")
    time.sleep(FETCH_INT)  # Wait for the specified interval before the next update
    i+=1