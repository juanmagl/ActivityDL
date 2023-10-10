import argparse
from datetime import datetime
from operator import itemgetter
import os
import threading
import time
import requests
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import dateutil.parser as dp


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
parser.add_argument('-d','--datefrom', help="specify initial date of the workouts")
parser.add_argument('-i', '--clientid', help="withings client_id")
parser.add_argument('-s', '--clientsecret', help="withings client_secret")
args = parser.parse_args()

if args.datefrom:
    args_date = dp.parse(args.datefrom)
    FROM_DATE = args_date.isoformat()
if args.clientid:
    CLIENT_ID = args.clientid
if args.clientsecret:
    CLIENT_SECRET = args.clientsecret

# Check if refresh_token exists and is valid
if os.path.isfile('.refresh_token'):
    # Open the file and read its contents
    with open('.refresh_token', 'r') as file:
        refresh_token = file.read()

# TODO: persist refresh_token in file if retrieved new
# TODO: Try access with refresh_token first, and seek authorization only if refresh_token not existant or invalid

def get_authorization_code(auth_url, client_id, redirect_url, callback_port):
    # Trigger a browser window for user authentication with some delay to allow for listener to start
    params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': 'user.info,user.activity',  # adjust scope as needed
        'state': 'some_random_string'  # protect against CSRF
    }

    # TODO: build auth_request with some parser
    auth_request = AUTH_URL + '?' + '&'.join([f'{k}={v}' for k, v in params.items()])

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
            params = parse_qs(query)
            self.server.auth_code = params.get('code', [None])[0]
        def log_message(self, format, *args):
            pass

    httpd = HTTPServer(('localhost', int(CALLBACK_PORT)), Handler)
    print("About to handle request")
    httpd.handle_request()  # handle one request then shutdown
    return httpd.auth_code

def get_access_tokens_auth(token_url, client_id, client_secret, auth_code):
    # Use the Authentication token to obtain Access and Refresh tokens
    data = {
        'action': 'requesttoken',
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': REDIRECT_URI,
        'code': auth_code
    }

    response = requests.post(token_url, data=data)
    tokens = response.json()
    #print(tokens)
    if tokens['status'] == 0:
        access_token = tokens['body']['access_token']
        refresh_token = tokens['body']['refresh_token']
    else:
        access_token = None
        print(f"Error: {tokens}")
    #print(access_token)
    return access_token, refresh_token

def get_access_tokens_refresh(token_url, client_id, client_secret, refresh_tok):
    data = {
        'action': 'requesttoken',
        'grant_type': 'refresh_token',
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_tok
    }

    response = requests.post(token_url, data=data)
    tokens = response.json()
    #print(tokens)
    if tokens['status'] == 0:
        access_token = tokens['body']['access_token']
        refresh_token = tokens['body']['refresh_token']
    else:
        access_token = None
        print(f"Error: {tokens}")
    #print(access_token)
    return access_token, refresh_token

def get_all_workouts_since(api_url, token, last_update):
    # Connect to Withings API with the Access token
    headers = {'Authorization': f'Bearer {token}'}
    params = {
        'action': 'getworkouts',
        'offset': 0,
        'lastupdate': last_update
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
    'data_fields': 'steps,distance,stroke,duration,heart_rate'
          }
    response = requests.post(api_url, headers=headers, params=params).json()

    if response['status'] == 0:
        details = response['body']['series']
    else:
        details = None
        print(f"Error: {response}")
    return details

auth_code = get_authorization_code(AUTH_URL, CLIENT_ID, REDIRECT_URI, CALLBACK_PORT)
access_token, refresh_token = get_access_tokens_auth(TOKEN_URL, CLIENT_ID, CLIENT_SECRET, auth_code)

from_date = int(dp.isoparse(FROM_DATE).timestamp())
print(f"Fetching workouts since {datetime.fromtimestamp(from_date)}")

all_workouts = get_all_workouts_since(API_URL, access_token, from_date)
lastworkout = all_workouts[-1]

startdate = lastworkout['startdate']
enddate = lastworkout['enddate']
print(f"Last workout: from {datetime.fromtimestamp(startdate)} to {datetime.fromtimestamp(enddate)}")

details = get_intradayactivity(API_URL, access_token, startdate, enddate)

print(f"There are {len(details)} details.")
