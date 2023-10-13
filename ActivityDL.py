import argparse
from datetime import datetime, timezone
import json
from operator import itemgetter
import os
import secrets
import sys
import threading
import time
import keyring
import requests
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, urlunparse, urlencode
import dateutil.parser as dp
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np


USE_KEYRING = True
VERSION = "1.0.0"
BUILD_TIME = "2023-10-10T17:30:00Z"
BUILDER_NAME = "JM"

def load_refresh_token_file():
    refresh_token = None
    if os.path.isfile('.refresh_token'):
        # Open the file and read its contents
        with open('.refresh_token', 'r') as file:
            refresh_token = file.read()
    return refresh_token

def save_refresh_token_file(refresh_token):
    with open('.refresh_token','w') as file:
        file.write(refresh_token)

def load_refresh_token_keyring():
    refresh_token = None
    refresh_token = keyring.get_password('ActivityDL','refresh_token')
    return refresh_token

def save_refresh_token_keyring(refresh_token):
    keyring.set_password('ActivityDL','refresh_token',refresh_token)
    pass

def load_refresh_token():
    if USE_KEYRING:
        return load_refresh_token_keyring()
    else:
        return load_refresh_token_file()

def save_refresh_token(refresh_token):
    if USE_KEYRING:
        save_refresh_token_keyring(refresh_token)
    else:
        save_refresh_token_file(refresh_token)

def get_authorization_code(auth_url, client_id, redirect_url, callback_port):
    # Trigger a browser window for user authentication with some delay to allow for listener to start
    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect_url,
        'scope': 'user.info,user.activity',  # adjust scope as needed
        'state': 'some_random_string'  # protect against CSRF
    }

    params['state'] = secrets.token_hex(32)

    # Build auth_request with parser
    # Raw method: auth_request = auth_url + '?' + '&'.join([f'{k}={v}' for k, v in params.items()])
    url_parts = list(urlparse(auth_url))
    url_parts[4] = urlencode(params)
    auth_request = urlunparse(url_parts)

    class ThreadedBrowser(object):
        def __init__(self,request="") -> None:
            self.request = request
            thread = threading.Thread(target=self.run, args=())
            thread.daemon = True
            thread.start()
        def run(self):
            time.sleep(0.5)
            print("About to launch browser")
            webbrowser.open(self.request)

    auth_browser = ThreadedBrowser(auth_request)

    # Receive the Authentication token via a running web server
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<h1>You can now close this window.</h1>')
            self.wfile.write(b'<script>window.close();</script>')
            query = urlparse(self.path).query
            response_params = parse_qs(query)
            self.server.auth_code = response_params.get('code', [None])[0]
            self.server.resp_state = response_params.get('state', [None])[0]
        def log_message(self, format, *args):
            pass

    httpd = HTTPServer(('localhost', int(callback_port)), Handler)
    print("About to handle request")
    httpd.handle_request()  # handle one request then shutdown
    if httpd.resp_state != params['state']:
        print(f"Error: {httpd.resp_state} != {params['state']}")
        sys.exit(2)
    return httpd.auth_code

def get_access_tokens_common(the_url, request_data):
    response = requests.post(the_url, data=request_data)
    tokens = response.json()
    #print(tokens)
    if tokens['status'] == 0:
        access_token = tokens['body']['access_token']
        refresh_token = tokens['body']['refresh_token']
    else:
        access_token = None
        refresh_token = None
        print(f"Error: {tokens}")
    #print(access_token)
    return access_token, refresh_token

def get_access_tokens_auth(token_url, client_id, client_secret, redirect_url, auth_code):
    # Use the Authentication token to obtain Access and Refresh tokens
    data = {
        'action': 'requesttoken',
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_url,
        'code': auth_code
    }
    return get_access_tokens_common(token_url, data)

def get_access_tokens_refresh(token_url, client_id, client_secret, refresh_tok):
    data = {
        'action': 'requesttoken',
        'grant_type': 'refresh_token',
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_tok
    }

    return get_access_tokens_common(token_url, data)

def get_all_workouts_since(api_url, token, last_update):
    # Connect to Withings API with the Access token
    headers = {'Authorization': f'Bearer {token}'}
    params = {
        'action': 'getworkouts',
        'offset': 0,
        'lastupdate': last_update,
        'data_fields': 'calories,intensity,manual_distance,manual_calories,' +
            'hr_average,hr_min,hr_max,hr_zone_0,hr_zone_1,hr_zone_2,hr_zone_3,' +
            'pause_duration,algo_pause_duration,spo2_average,steps,distance,elevation,pool_laps,strokes,pool_length'
            }
    more = True

    all_workouts = []
    while more:
        response = requests.post(api_url, headers=headers, params=params).json()

        if response['status'] == 0:
            workouts = response['body']['series']
            more = response['body']['more']
            offset = response['body']['offset']
            all_workouts.extend(workouts)

            if more:
                params['offset'] = offset
            print(f"Workouts obtained: {len(workouts)}, More: {more}, Total workouts: {len(all_workouts)}")
        else:
            workouts = None
            more = False
            offset = None
            print(f"Error: {response}")

    # Inform how many workouts were retrieved
    print(f"Total number of workouts: {len(all_workouts)}")

    all_workouts.sort(key=itemgetter('startdate','id'), reverse=False)
    return all_workouts

def get_intradayactivity(api_url, access_token, startdate, enddate):
    # Get the activity detail for the workout
    headers = {'Authorization': f'Bearer {access_token}'}
    params = {
    'action': 'getintradayactivity',
    'startdate': startdate,
    'enddate': enddate,
    'data_fields': 'steps,elevation,calories,distance,stroke,pool_lap,duration,heart_rate,spo2_auto'
          }
    response = requests.post(api_url, headers=headers, params=params).json()

    if response['status'] == 0:
        details = response['body']['series']

    else:
        details = None
        print(f"Error: {response}")
    return details

def timestamp_to_iso8601(ts):
    return datetime.fromtimestamp(ts,tz=timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

def create_tcx(workout, details):
    # Parent is the parent element
    # Data is a dictionary with the key as the tag name and the value as the text in it
    
    class trialContextManager:
        def __enter__(self): pass
        def __exit__(self, *args): return True
    
    trial = trialContextManager()
    
    def createElementSeries(parent, data):
        for k, v in data.items():
            elem = ET.SubElement(parent, k)
            elem.text = v

    # Model names obtained from:
    # https://developer.withings.com/api-reference/#tag/measure/operation/measurev2-getworkouts
    # https://developer.withings.com/api-reference/#tag/measure/operation/measurev2-getintradayactivity
    model_names = {'1': 'Withings WBS01', '2': 'Withings WS30', '3': 'Kid Scale', '4': 'Smart Body Analyzer',
                   '5': 'Body+', '6': 'Body Cardio', '7': 'Body', '9': 'Body Pro', '10': 'Body Scan', '11': 'WBS10',
                   '12': 'WBS11', '13': 'Body+, type: 1', '21': 'Smart Baby Monitor', '22': 'Withings Home',
                   '41': 'Withings Blood Pressure Monitor V1', '42': 'Withings Blood Pressure Monitor V2',
                   '43': 'Withings Blood Pressure Monitor V3', '44': 'BPM Core', '45': 'BPM Connect',
                   '46': 'BPM Connect Pro', '51': 'Pulse', '52': 'Activite', '53': 'Activite (Pop, Steel)',
                   '54': 'Withings Go', '55': 'Activite', 'Steel': 'HR', '58': 'Pulse HR',
                   '59': 'Activite Steel HR Sport Edition', '60': 'Aura Dock', '61': 'Aura Sensor', '62': 'Aura dock,',
                   '63': 'Aura Sensor V2', '70': 'Thermo', '90': 'Move', '91': 'Move ECG', '92': 'Move ECG', '93': 'ScanWatch',
                   '100': 'WUP01', '1051': 'iOS step tracker', '1052': 'iOS step tracker', '1053': 'Android step tracker',
                   '1054': 'Android step tracker', '1055': 'GoogleFit tracker', '1056': 'Samsung Health tracker',
                   '1057': 'HealthKit step iPhone tracker', '1058': 'HealthKit step Apple Watch tracker',
                   '1059': 'HealthKit other', 'step': 'tracker', '1060': 'Android step tracker', '1061': 'Iglucose glucometer',
                   '1062': 'Huawei tracker'}
    # Sport names obtained from:
    # https://developer.withings.com/api-reference/#tag/measure/operation/measurev2-getworkouts
    # The following should be the real list of sport names, but tcx schema only accepts 'Running', 'Biking', 'Other'
    sport_names = {'1': 'Walk', '2': 'Run', '3': 'Hiking', '4': 'Skating', '5': 'BMX', '6': 'Bicycling', '7': 'Swimming',
                   '8': 'Surfing', '9': 'Kitesurfing', '10': 'Windsurfing', '11': 'Bodyboard', '12': 'Tennis',
                   '13': 'Table tennis', '14': 'Squash', '15': 'Badminton', '16': 'Lift weights', '17': 'Calisthenics',
                   '18': 'Elliptical', '19': 'Pilates', '20': 'Basket-ball', '21': 'Soccer', '22': 'Football',
                   '23': 'Rugby', '24': 'Volley-ball', '25': 'Waterpolo', '26': 'Horse riding', '27': 'Golf',
                   '28': 'Yoga', '29': 'Dancing', '30': 'Boxing', '31': 'Fencing', '32': 'Wrestling',
                   '33': 'Martial arts', '34': 'Skiing', '35': 'Snowboarding', '36': 'Other', '128': 'No activity',
                   '187': 'Rowing', '188': 'Zumba', '191': 'Baseball', '192': 'Handball', '193': 'Hockey',
                   '194': 'Ice hockey', '195': 'Climbing', '196': 'Ice skating', '272': 'Multi-sport',
                   '306': 'Indoor walk', '307': 'Indoor running', '308': 'Indoor cycling'}
    # This dict maps withings sport codes to tcx sport codes
    sport_names_tcx = {'1': 'Other', '2': 'Running', '3': 'Other', '4': 'Other', '5': 'Biking', '6': 'Biking', '7': 'Other',
                   '8': 'Other', '9': 'Other', '10': 'Other', '11': 'Other', '12': 'Other',
                   '13': 'Other', '14': 'Other', '15': 'Other', '16': 'Other', '17': 'Other',
                   '18': 'Other', '19': 'Other', '20': 'Other', '21': 'Other', '22': 'Other',
                   '23': 'Other', '24': 'Other', '25': 'Other', '26': 'Other', '27': 'Other',
                   '28': 'Other', '29': 'Other', '30': 'Other', '31': 'Other', '32': 'Other',
                   '33': 'Other', '34': 'Other', '35': 'Other', '36': 'Other', '128': 'Other',
                   '187': 'Other', '188': 'Other', '191': 'Other', '192': 'Other', '193': 'Other',
                   '194': 'Other', '195': 'Other', '196': 'Other', '272': 'Other',
                   '306': 'Other', '307': 'Running', '308': 'Biking'}

    sportname = "Other"
    sportname_tcx = "Other"
    starttime_ts = int(workout['startdate'])
    endtime_ts = int(workout['enddate'])
    starttime = timestamp_to_iso8601(0)
    endtime = starttime
    total_duration = 0.0
    total_distance = 0.0
    total_calories = 0
    hr_avg = 0
    hr_max = 0
    cadence_avg = 0

    with trial: starttime = timestamp_to_iso8601(starttime_ts)
    with trial: endtime = timestamp_to_iso8601(endtime_ts)
    with trial: total_duration = float(endtime_ts - starttime_ts)
    with trial: total_distance = float(workout['data']['distance'])
    with trial: total_calories = int(workout['data']['calories'])
    with trial: hr_avg = int(workout['data']['hr_average'])
    with trial: hr_max = int(workout['data']['hr_max'])
    with trial: cadence_avg = int(float(workout['data']['steps']) / (total_duration/60.0))

    distance = 0.0
    tcx_elt = ET.Element("TrainingCenterDatabase",
        {"xmlns": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"})
    activities_elt = ET.SubElement(tcx_elt, "Activities")
    sport = str(workout['category'])
    if sport in sport_names:
        sportname = sport_names[sport]
        sportname_tcx = sport_names_tcx[sport]
    activity_elt = ET.SubElement(activities_elt, "Activity", {'Sport': sportname_tcx})
    d = ET.SubElement(activity_elt, 'Id')
    d.text = starttime
    # Include activity data
    lap_elt = ET.SubElement(activity_elt,'Lap', {'StartTime': starttime})
    total_time_elt = ET.SubElement(lap_elt, 'TotalTimeSeconds')
    total_time_elt.text = str(total_duration)
    total_distance_elt = ET.SubElement(lap_elt, 'DistanceMeters')
    total_distance_elt.text = str(total_distance)
    calories_elt = ET.SubElement(lap_elt, 'Calories')
    calories_elt.text = str(total_calories)
    hr_avg_elt = ET.SubElement(lap_elt, 'AverageHeartRateBpm')
    createElementSeries(hr_avg_elt, {'Value': str(hr_avg)})
    hr_max_elt = ET.SubElement(lap_elt, 'MaximumHeartRateBpm')
    createElementSeries(hr_max_elt, {'Value': str(hr_max)})
    createElementSeries(lap_elt, {'Intensity': 'Active'})
    cadence_elt = ET.SubElement(lap_elt, 'Cadence')
    cadence_elt.text = str(cadence_avg)
    createElementSeries(lap_elt, {'TriggerMethod': 'Manual'})
    track_elt = ET.SubElement(lap_elt, 'Track')
    # TODO: Calculate avg cadence, total distance
    cumul_steps = 0
    cumul_dist = 0.0
    for pt_ts in sorted(details.keys(), reverse=False):
        det = details[pt_ts]
        pt_time = timestamp_to_iso8601(int(pt_ts))
        hr, dur, steps, elev, dist, cal = None, None, None, None, None, None
        with trial: hr = det['heart_rate']
        with trial: dur = det['duration']
        with trial: steps = det['steps']
        with trial: elev = det['elevation']
        with trial: dist = det['distance']
        with trial: cal = det['calories']
        # print(pt_time, hr, dur, steps, elev, dist, cal)
        # 2023-10-11T18:56:54Z 159 1 None None None None
        # 2023-10-11T18:56:56Z 158 2 None None None None
        # 2023-10-11T18:56:59Z 158 3 None None None None
        # 2023-10-11T18:57:00Z None 60 132 None 112.42 3.7
        # 2023-10-11T18:57:01Z 157 2 None None None None
        # 2023-10-11T18:57:05Z 157 4 None None None None
        # 2023-10-11T18:57:07Z 156 2 None None None None
    df = pd.DataFrame.from_dict(details, orient='index')
    
    # Resample index to every second in interval
    df.index = pd.to_datetime(df.index.astype(int), unit='s', utc=True)
    hf_df = pd.date_range(start=starttime, freq='1s', periods=int(total_duration)).to_frame()
    df = pd.concat([df,hf_df])
    # Delete duplicates
    df = df[~df.index.duplicated(keep='first')]
    df['Time'] = df.index.map(lambda x: timestamp_to_iso8601(int(x.timestamp())))

    # Interpolate heart rate
    df['heart_rate'].interpolate(method='nearest', inplace=True)

    print(df.columns)
    print(df.dtypes)
    print(df)
    def create_trackpoint(p):
        trackpoint_elt = ET.SubElement(track_elt, 'Trackpoint')
        createElementSeries(trackpoint_elt, {'Time': str(p['Time'])})
        hr_elt = ET.SubElement(trackpoint_elt, 'HeartRateBpm')
        hr_val = int(1)
        with trial: hr_val = int(p['heart_rate'])
        createElementSeries(hr_elt, {'Value': str(hr_val)})
        cadence_elt = ET.SubElement(trackpoint_elt, 'Cadence')
        cadence_elt.text = '0'
        sensorstate_elt = ET.SubElement(trackpoint_elt, 'SensorState')
        sensorstate_elt.text = 'Present'
    df.apply(create_trackpoint, axis=1)
    # TODO: Check that this is applied in sorted way


    notes = ET.SubElement(activity_elt, 'Notes')
    notes.text = f"Withings sport name: {sportname}"
    creator_elt = ET.SubElement(activity_elt, 'Creator')
    creator_elt.set('xsi:type', "Device_t")
    creatorname = ET.SubElement(creator_elt, 'Name')
    creatorname.text = ""
    unitid = ET.SubElement(creator_elt, "UnitId")
    unitid.text = str(int(workout['deviceid'], 16) % 0x100000000)
    productid = ET.SubElement(creator_elt, 'ProductID') # Must be 'ProductID', not 'ProductId' for schema compliance
    productid.text = str(workout['model'])
    if productid.text in model_names:
        creatorname.text = model_names[productid.text]
    version = ET.SubElement(creator_elt, 'Version')
    version_data = {'VersionMajor': '0', 'VersionMinor': '1',
                    'BuildMajor': '0', 'BuildMinor': '1'}
    createElementSeries(version, version_data)
    author_elt = ET.SubElement(tcx_elt, 'Author')
    author_elt.set('xsi:type', "Application_t")
    elem = ET.SubElement(author_elt, 'Name')
    elem.text = 'ActivityDL'
    build = ET.SubElement(author_elt, 'Build')
    version = ET.SubElement(build, 'Version')
    version_data = {'VersionMajor': '0', 'VersionMinor': '1',
                    'BuildMajor': '0', 'BuildMinor': '1'}
    createElementSeries(version, version_data)
    build_data = {'Type': 'Internal', 'Time': BUILD_TIME,
                    'Builder': BUILDER_NAME}
    createElementSeries(build, build_data)
    elem = ET.SubElement(author_elt, 'LangID')
    elem.text = 'EN'
    elem = ET.SubElement(author_elt, 'PartNumber')
    elem.text = 'XXX-XXXXX-XX'

    return tcx_elt

def main():
    # Get these from your environment variables
    CLIENT_ID = os.environ.get('WITHINGS_CLIENT_ID','0000')
    CLIENT_SECRET = os.environ.get('WITHINGS_CLIENT_SECRET','0000')
    CALLBACK_PORT = os.environ.get('WITHINGS_CALLBACK_PORT','8000')
    REDIRECT_URI = 'http://localhost:' + CALLBACK_PORT
    AUTH_URL = 'https://account.withings.com/oauth2_user/authorize2'
    TOKEN_URL = 'https://wbsapi.withings.net/v2/oauth2'
    API_URL = 'https://wbsapi.withings.net/v2/measure'

    FROM_DATE = os.environ.get('FROM_DATE','1970-01-01T00:00:00Z')

    parser = argparse.ArgumentParser(description="fetch Withings activity data")
    parser.add_argument('-d', '--datefrom', help="specify initial date of the workouts")
    parser.add_argument('-i', '--clientid', help="withings client_id")
    parser.add_argument('-s', '--clientsecret', help="withings client_secret")
    parser.add_argument('-k', '--donotusekeyring', help="do not use keyring to store refresh tokens and instead store in a file", action='store_true')
    parser.add_argument('-v', '--version', action='version', version=VERSION)
    args = parser.parse_args()

    if args.datefrom:
        args_date = dp.parse(args.datefrom)
        FROM_DATE = args_date.isoformat()
    if args.clientid:
        CLIENT_ID = args.clientid
    if args.clientsecret:
        CLIENT_SECRET = args.clientsecret
    if args.donotusekeyring:
        global USE_KEYRING
        USE_KEYRING = False

    # Check if refresh_token exists and is valid
    access_token = None
    refresh_token = load_refresh_token()
    if refresh_token is not None:
        access_token, refresh_token = get_access_tokens_refresh(TOKEN_URL, CLIENT_ID, CLIENT_SECRET, refresh_token)
    if access_token is None:
        # Need to get authorization code
        auth_code = get_authorization_code(AUTH_URL, CLIENT_ID, REDIRECT_URI, CALLBACK_PORT)
        access_token, refresh_token = get_access_tokens_auth(TOKEN_URL, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, auth_code)
    save_refresh_token(refresh_token)


    from_date = int(dp.isoparse(FROM_DATE).timestamp())
    print(f"Fetching workouts since {datetime.fromtimestamp(from_date)}")

    all_workouts = get_all_workouts_since(API_URL, access_token, from_date)
    thiswkout = all_workouts[-1]

    startdate_ts = thiswkout['startdate']
    enddate_ts = thiswkout['enddate']
    startdate_str = datetime.fromtimestamp(startdate_ts)
    enddate_str = datetime.fromtimestamp(enddate_ts)
    print(f"Last workout: from {startdate_str} to {enddate_str}")

    act_details = get_intradayactivity(API_URL, access_token, startdate_ts, enddate_ts)

    print(f"There are {len(act_details)} details.")

    # print(json.dumps(thiswkout, indent=2))
    # {
    #   "id": 3753040381,
    #   "category": 307,
    #   "timezone": "Europe/Madrid",
    #   "model": 93,
    #   "attrib": 7,
    #   "startdate": 1697049003,
    #   "enddate": 1697050807,
    #   "date": "2023-10-11",
    #   "deviceid": "XXXXXXXXXXX",
    #   "data": {
    #     "calories": 114.39999389648,
    #     "intensity": 50,
    #     "hr_average": 138,
    #     "hr_min": 84,
    #     "hr_max": 176,
    #     "hr_zone_0": 0,
    #     "hr_zone_1": 351,
    #     "hr_zone_2": 773,
    #     "hr_zone_3": 621,
    #     "pause_duration": 3,
    #     "steps": 3775,
    #     "distance": 3054.3000488281,
    #     "manual_distance": null,
    #     "manual_calories": null,
    #     "algo_pause_duration": null,
    #     "spo2_average": null,
    #     "elevation": null
    #   },
    #   "modified": 1697053462
    # }


    # print(json.dumps(act_details, indent=2))
    #   "1697050739": {
    #     "heart_rate": 133,
    #     "duration": 4,
    #     "model": "ScanWatch",
    #     "model_id": 93,
    #     "deviceid": "XXXXXXXXXXX"
    #   },
    #   "1697050740": {
    #     "steps": 72,
    #     "duration": 60,
    #     "distance": 52.33,
    #     "calories": 1.72,
    #     "model": "ScanWatch",
    #     "model_id": 93,
    #     "deviceid": "XXXXXXXXXXX"
    #   },
    #   "1697050744": {
    #     "heart_rate": 128,
    #     "duration": 5,
    #     "model": "ScanWatch",
    #     "model_id": 93,
    #     "deviceid": "XXXXXXXXXXX"
    #   },
    

    tcx = create_tcx(thiswkout, act_details)
    ET.indent(tcx)
    ET.dump(tcx)
    ET.ElementTree(tcx).write(''.join([timestamp_to_iso8601(startdate_ts), '.tcx']))

if __name__ == '__main__':
    main()