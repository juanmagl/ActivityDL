import os
import requests
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

# Get these from your environment variables
CLIENT_ID = os.getenv('WITHINGS_CLIENT_ID')
CLIENT_SECRET = os.getenv('WITHINGS_CLIENT_SECRET')
REDIRECT_URI = 'http://localhost:8000'
AUTH_URL = 'https://account.withings.com/oauth2_user/authorize2'
TOKEN_URL = 'https://wbsapi.withings.net/v2/oauth2'
API_URL = 'https://wbsapi.withings.net/v2/measure'

# Step 1: Trigger a browser window for user authentication
params = {
    'response_type': 'code',
    'client_id': CLIENT_ID,
    'redirect_uri': REDIRECT_URI,
    'scope': 'user.activity',  # adjust scope as needed
    'state': 'some_random_string'  # protect against CSRF
}
webbrowser.open(AUTH_URL + '?' + '&'.join([f'{k}={v}' for k, v in params.items()]))

# Step 2: Receive the Authentication token via a running web server
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.server.auth_code = self.path.split('?')[1].split('=')[1]

httpd = HTTPServer(('localhost', 8000), Handler)
httpd.handle_request()  # handle one request then shutdown

print(httpd.auth_code)
# Step 3: Use the Authentication token to obtain Access and Refresh tokens
data = {
    'grant_type': 'authorization_code',
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'redirect_uri': REDIRECT_URI,
    'code': httpd.auth_code
}
response = requests.post(TOKEN_URL, data=data)
tokens = response.json()
access_token = tokens['access_token']

# Step 4: Connect to Withings API with the Access token
headers = {'Authorization': f'Bearer {access_token}'}
params = {'action': 'getactivity'}
response = requests.post(API_URL, headers=headers, params=params)
activities = response.json()['body']['activities']

# Step 5: List the activities as standard output
for activity in activities[:10]:  # get the 10 most recent activities
    print(activity)
