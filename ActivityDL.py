import os
import requests
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from datetime import datetime


# Get these from your environment variables
CLIENT_ID = os.getenv('WITHINGS_CLIENT_ID')
CLIENT_SECRET = os.getenv('WITHINGS_CLIENT_SECRET')
CALLBACK_PORT = os.getenv('WITHINGS_CALLBACK_PORT')
REDIRECT_URI = 'http://localhost:' + CALLBACK_PORT
AUTH_URL = 'https://account.withings.com/oauth2_user/authorize2'
TOKEN_URL = 'https://wbsapi.withings.net/v2/oauth2'
API_URL = 'https://wbsapi.withings.net/v2/measure'

# Step 1: Trigger a browser window for user authentication
params = {
    'response_type': 'code',
    'client_id': CLIENT_ID,
    'redirect_uri': REDIRECT_URI,
    'scope': 'user.info,user.activity',  # adjust scope as needed
    'state': 'some_random_string'  # protect against CSRF
}
webbrowser.open(AUTH_URL + '?' + '&'.join([f'{k}={v}' for k, v in params.items()]))

# Step 2: Receive the Authentication token via a running web server
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

httpd = HTTPServer(('localhost', int(CALLBACK_PORT)), Handler)
httpd.handle_request()  # handle one request then shutdown

# Step 3: Use the Authentication token to obtain Access and Refresh tokens
data = {
    'action': 'requesttoken',
    'grant_type': 'authorization_code',
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'redirect_uri': REDIRECT_URI,
    'code': httpd.auth_code
}

response = requests.post(TOKEN_URL, data=data)
tokens = response.json()
#print(tokens)
if tokens['status'] == 0:
    access_token = tokens['body']['access_token']
else:
    access_token = None
    print(f"Error: {tokens}")
#print(access_token)

# Step 4: Connect to Withings API with the Access token
headers = {'Authorization': f'Bearer {access_token}'}
params = {
    'action': 'getworkouts',
    'offset': 0
          }
more = True

all_workouts = []

while more:
    response = requests.post(API_URL, headers=headers, params=params).json()

    if response['status'] == 0:
        workouts = response['body']['series']
        more = response['body']['more']
        offset = response['body']['offset']
        all_workouts.extend(workouts)

        if more:
            params['offset'] = offset
        print(f"Workouts obtained: {len(workouts)}, More: {more}, Offset: {offset}. Total workouts: {len(all_workouts)}")
    else:
        workouts = None
        more = False
        offset = None
        print(f"Error: {response}")

# Step 5: Inform how many workouts were retrieved
print(f"Number of workouts: {len(all_workouts)}")

lastworkout = all_workouts[-1:][0]
print(f"Id: {lastworkout['id']}, Start: {datetime.fromtimestamp(lastworkout['startdate'])}, End: {datetime.fromtimestamp(lastworkout['enddate'])}")

startdate = lastworkout['startdate']
enddate = lastworkout['enddate']

# Step 6: Get the activity detail for the workout
headers = {'Authorization': f'Bearer {access_token}'}
params = {
    'action': 'getintradayactivity',
    'startdate': startdate,
    'enddate': enddate,
    'data_fields': 'steps,distance,stroke,duration,heart_rate'
          }
response = requests.post(API_URL, headers=headers, params=params).json()

if response['status'] == 0:
    workouts = response['body']['series']
else:
    workouts = None
    print(f"Error: {response}")

print(f"There are {len(workouts)} details.")
