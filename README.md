# ActivityDL

ActivityDL is a Python script that interacts with the Withings API to retrieve and export workout data in TCX (Training Center XML) format. This script allows you to list Withings workouts and fetch them as .tcx files. It supports exporting all workouts since a specified initial date or exporting only the first workout since the initial date.

## Prerequisites

Before using the script, make sure you have the following:

- Withings Developer Account: Create a developer account on [Withings Developer](https://developer.withings.com/).
- Withings API Credentials: Obtain the `CLIENT_ID` and `CLIENT_SECRET` by creating a new application on the Withings Developer portal.
- Python Environment: Ensure you have Python installed on your machine.

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/your-username/ActivityDL.git
   ```

2. Navigate to the project directory:

   ```bash
   cd ActivityDL
   ```

3. Install the required Python packages:

   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the script with the following command:

```bash
python ActivityDL.py [options]
```

### Options

- `-d, --datefrom`: Specify the initial date of the workouts.
- `-a, --all`: Export all workouts since the initial date as .tcx files.
- `-1, --one`: Export only the first workout since the initial date as a .tcx file.
- `-i, --clientid`: Withings client_id.
- `-s, --clientsecret`: Withings client_secret.
- `-k, --donotusekeyring`: Do not use keyring to store refresh tokens; instead, store in a file.
- `-v, --version`: Show the script version.
- `-t, --autodetected`: Include autodetected workouts (not confirmed by the user). Default is only confirmed.
- `-g, --gpxfile`: GPX file with location information.
- `--donotupdatedistance`: If set, do not update TCX total distance with calculated distance from GPX.

### Environment Variables

Set the following environment variables:

- `WITHINGS_CLIENT_ID`: Your Withings client_id.
- `WITHINGS_CLIENT_SECRET`: Your Withings client_secret.
- `WITHINGS_CALLBACK_PORT`: Port number for the callback (default is 8000).
- `FROM_DATE`: Initial date for workouts in ISO format (default is '1970-01-01T00:00:00Z').

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.