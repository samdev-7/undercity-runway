import time
import requests
import logging
from math import radians, cos, sin
from datetime import datetime, timedelta, timezone
from threading import Lock

# Logging configuration
ENABLE_LOGGING = True
if ENABLE_LOGGING:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
else:
    logging.basicConfig(level=logging.ERROR)

# Configuration Parameters
API_KEY = "KEY"

# Runway Definitions for ATL
RECTANGLES = [
    ("8R-26L", 33.6407, -84.4277, 0.15, 4.0, 80.0),
    ("8L-26R", 33.6330, -84.4200, 0.15, 3.8, 80.0),
    ("9L-27R", 33.6480, -84.4350, 0.15, 2.7, 90.0),
    ("9R-27L", 33.6320, -84.4150, 0.15, 2.7, 90.0),
    ("10-28", 33.6290, -84.4380, 0.15, 3.0, 100.0)
]

KM_PER_DEG_LAT = 111
KM_PER_DEG_LON = 111

recent_flights = {}
FLIGHT_MEMORY_MINUTES = 15

last_api_call = 0
API_RATE_LIMIT = 1.0
api_lock = Lock()
api_call_count = 0
api_call_window_start = time.time()
MAX_CALLS_PER_MINUTE = 60

def rate_limited_request(url, headers, params=None):
    global last_api_call, api_call_count, api_call_window_start

    with api_lock:
        current_time = time.time()
        if current_time - api_call_window_start > 60:
            api_call_count = 0
            api_call_window_start = current_time

        if api_call_count >= MAX_CALLS_PER_MINUTE:
            sleep_time = 60 - (current_time - api_call_window_start)
            if sleep_time > 0:
                logging.warning(f"Rate limit reached, sleeping for {sleep_time:.1f} seconds")
                time.sleep(sleep_time)
                api_call_count = 0
                api_call_window_start = time.time()

        time_since_last = current_time - last_api_call
        if time_since_last < API_RATE_LIMIT:
            time.sleep(API_RATE_LIMIT - time_since_last)

        try:
            logging.info(f"Making API request to: {url}")
            logging.info(f"Parameters: {params}")

            response = requests.get(url, headers=headers, params=params, timeout=15)
            last_api_call = time.time()
            api_call_count += 1
            logging.info(f"Response status: {response.status_code}")

            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                logging.warning(f"Rate limited by server, waiting {retry_after} seconds")
                time.sleep(retry_after)
                return None

            if response.status_code == 400:
                logging.error(f"Bad request (400): {response.text}")
                return None

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logging.error(f"API request failed: {e}")
            if "429" in str(e):
                logging.warning("Rate limit exceeded, increasing delay")
                time.sleep(60)
            return None

def is_point_in_rotated_rectangle(flight_lat, flight_lon, center_lat, center_lon, width_km, height_km, angle_deg):
    km_per_deg_lon = KM_PER_DEG_LON * cos(radians(center_lat))
    dx = (flight_lon - center_lon) * km_per_deg_lon
    dy = (flight_lat - center_lat) * KM_PER_DEG_LAT

    angle_rad = radians(-angle_deg)
    x_rot = dx * cos(angle_rad) - dy * sin(angle_rad)
    y_rot = dx * sin(angle_rad) + dy * cos(angle_rad)

    return abs(x_rot) <= width_km / 2 and abs(y_rot) <= height_km / 2

def get_runway_for_flight(flight_lat, flight_lon):
    for label, center_lat, center_lon, width_km, height_km, angle_deg in RECTANGLES:
        if is_point_in_rotated_rectangle(flight_lat, flight_lon, center_lat, center_lon, width_km, height_km, angle_deg):
            return label
    return None

def get_atl_flights():
    flights_data = {'arrivals': [], 'departures': []}

    headers = {
        'x-apikey': API_KEY,
        'Accept': 'application/json; charset=UTF-8'
    }

    now = datetime.now(timezone.utc)
    params = {
        'max_pages': 1,
        'start': (now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'end': (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    }

    arrivals_url = "https://aeroapi.flightaware.com/aeroapi/airports/KATL/flights/arrivals"
    arrivals_data = rate_limited_request(arrivals_url, headers, params)
    if arrivals_data:
        flights_data['arrivals'] = arrivals_data.get('arrivals', [])[:10]

    departures_url = "https://aeroapi.flightaware.com/aeroapi/airports/KATL/flights/departures"
    departures_data = rate_limited_request(departures_url, headers, params)
    if departures_data:
        flights_data['departures'] = departures_data.get('departures', [])[:10]

    return flights_data

def get_flight_position(flight_id):
    url = f"https://aeroapi.flightaware.com/aeroapi/flights/{flight_id}/position"
    headers = {
        'x-apikey': API_KEY,
        'Accept': 'application/json; charset=UTF-8'
    }

    data = rate_limited_request(url, headers)
    if data:
        positions = data.get('positions', [])
        if positions:
            latest_pos = positions[-1]
            return {
                'latitude': latest_pos.get('latitude'),
                'longitude': latest_pos.get('longitude'),
                'altitude': latest_pos.get('altitude'),
                'timestamp': latest_pos.get('timestamp')
            }
    return None

def is_flight_on_runway_8r_26l(flight_data):
    flight_id = flight_data.get('fa_flight_id')
    if not flight_id:
        return False, None

    if flight_id in recent_flights:
        if recent_flights[flight_id].get('runway') == "8R-26L":
            return True, "8R-26L"

    position = get_flight_position(flight_id)
    if not position or not position.get('latitude') or not position.get('longitude'):
        return False, None

    runway = get_runway_for_flight(position['latitude'], position['longitude'])
    if runway == "8R-26L":
        return True, runway

    return False, None

def clean_old_flights():
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(minutes=FLIGHT_MEMORY_MINUTES)

    for flight_id in list(recent_flights):
        if recent_flights[flight_id]['timestamp'] < cutoff_time:
            del recent_flights[flight_id]

def check_runway_activity():
    try:
        current_time = datetime.now()
        new_arrivals = []
        new_departures = []

        flights_data = get_atl_flights()

        for arrival in flights_data['arrivals'][:3]:
            flight_id = arrival.get('fa_flight_id')
            if not flight_id or flight_id in recent_flights:
                continue

            status = arrival.get('status', '')
            actual_arrival = arrival.get('actual_arrival_time')

            if not actual_arrival or not any(k in status.lower() for k in ['landed', 'arrived', 'completed', 'taxiing']):
                continue

            try:
                arrival_time = datetime.fromisoformat(actual_arrival.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) - arrival_time > timedelta(minutes=30):
                    continue
            except:
                continue

            on_runway, runway = is_flight_on_runway_8r_26l(arrival)
            if not on_runway:
                continue

            flight_info = {
                'runway': runway,
                'type': 'ARRIVAL',
                'timestamp': current_time,
                'origin': arrival.get('origin', {}).get('code', 'Unknown'),
                'arrival_time': actual_arrival
            }

            recent_flights[flight_id] = flight_info
            new_arrivals.append(flight_info)

        for departure in flights_data['departures'][:3]:
            flight_id = departure.get('fa_flight_id')
            if not flight_id or flight_id in recent_flights:
                continue

            status = departure.get('status', '')
            actual_departure = departure.get('actual_departure_time')

            if not actual_departure or not any(k in status.lower() for k in ['departed', 'en route', 'airborne', 'taxiing']):
                continue

            try:
                departure_time = datetime.fromisoformat(actual_departure.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) - departure_time > timedelta(minutes=30):
                    continue
            except:
                continue

            on_runway, runway = is_flight_on_runway_8r_26l(departure)
            if not on_runway:
                continue

            flight_info = {
                'runway': runway,
                'type': 'DEPARTURE',
                'timestamp': current_time,
                'destination': departure.get('destination', {}).get('code', 'Unknown'),
                'departure_time': actual_departure
            }

            recent_flights[flight_id] = flight_info
            new_departures.append(flight_info)

        clean_old_flights()

        return new_arrivals, new_departures

    except Exception as e:
        logging.error(f"Error checking runway activity: {e}")
        return [], []

def control_motor_for_arrival():
    print("🛬 ARRIVAL ANIMATION - Moving plane to arrival position")
    time.sleep(5)
    print("✅ Arrival animation complete")

def control_motor_for_departure():
    print("🛫 DEPARTURE ANIMATION - Moving plane to departure position")
    time.sleep(5)
    print("✅ Departure animation complete")

def main_loop():
    print("🚀 Starting ATL Runway 8R/26L Monitor")
    if API_KEY == "your_flightaware_api_key_here":
        print("⚠️  Please update your API key.")
        return

    consecutive_errors = 0
    while True:
        try:
            arrivals, departures = check_runway_activity()
            consecutive_errors = 0

            for arrival in arrivals:
                print(f"🛬 ARRIVAL from {arrival['origin']} on {arrival['runway']}")
                control_motor_for_arrival()

            for departure in departures:
                print(f"🛫 DEPARTURE to {departure['destination']} on {departure['runway']}")
                control_motor_for_departure()

            if not arrivals and not departures:
                print("⏳ No new activity on 8R/26L")

            print(f"💾 Tracked flights: {len(recent_flights)}")
            print(f"📊 API calls this minute: {api_call_count}")

            time.sleep(180)

        except KeyboardInterrupt:
            print("\n🛑 Stopped by user")
            break
        except Exception as e:
            consecutive_errors += 1
            logging.error(f"Main loop error #{consecutive_errors}: {e}")
            if consecutive_errors >= 5:
                print(f"❌ Too many errors ({consecutive_errors}), exiting...")
                break
            time.sleep(min(60, 10 * (2 ** consecutive_errors)))

if __name__ == "__main__":
    main_loop()