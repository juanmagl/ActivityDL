import requests
from flask import Flask, request
from requests.auth import HTTPBasicAuth
import webbrowser

# Variables for common API URL parameters
client_id = 'your_client_id'
client_secret = 'your_client_secret'
redirect_uri = 'your_redirect_uri'  # This should be the URL of your running web server
state = 'your_state'  # This can be any string

# Create a Flask app for the running web server
app = Flask(__name__)

@app.route('/')
def home():
    code = request.args.get('code')
    if code:
        # Use the Authentication token to obtain the Access token
        token_url = 'https://account.withings.com/oauth2/token'
        token_data = {
            'grant_type': 'authorization_code',
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
        }
        response = requests.post(token_url, data=token_data, auth=HTTPBasicAuth(client_id, client_secret))
        access_token = response.json()['access_token']

        # Connect to Withings API with the Access token to obtain a list of the 10 most recent user activities
        activities_url = 'https://wbsapi.withings.net/v2/measure?action=getactivity'
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(activities_url, headers=headers)
        activities = response.json()['body']['activities']

        # List the activities as output
        for activity in activities[:10]:
            print(f"Date: {activity['date']}, Steps: {activity['steps']}")
    else:
        return "No code provided"

    return "Success"

if __name__ == '__main__':
    # Trigger a browser window to authenticate the user
    auth_url = f'https://account.withings.com/oauth2_user/authorize2?response_type=code&client_id={client_id}&state={state}&scope=user.activity&redirect_uri={redirect_uri}'
    webbrowser.open(auth_url)

    # Run the web server
    app.run(port=5000)
