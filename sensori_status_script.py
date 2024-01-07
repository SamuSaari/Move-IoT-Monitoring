import os
import datetime
import pytz
from google.cloud import firestore
import requests
from influxdb_client import InfluxDBClient, Point, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS
#import smtplib
#from email.mime.multipart import MIMEMultipart
#from email.mime.text import MIMEText

# Initialize Firestore Client
db = firestore.Client()

# Initialize InfluxDB Client
influxdb_url = os.environ.get("INFLUXDB_URL")
influxdb_token = os.environ.get("INFLUXDB_TOKEN")
influxdb_org = os.environ.get("INFLUXDB_ORG")
influxdb_bucket = os.environ.get("INFLUXDB_BUCKET")

influxdb_client = InfluxDBClient(url=influxdb_url, token=influxdb_token, org=influxdb_org)
write_api = influxdb_client.write_api(write_options=SYNCHRONOUS)

# Define your Firestore collection reference for sensor status
status_collection = db.collection("sensors_grouped")

# Pushover API and User Key (retrieved from environment variables)
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")

# Move Solutions API and define sensors to monitor
API_KEY = os.environ.get("API_KEY")
BASE_URL = os.environ.get("BASE_URL")
STRUCTURE_ID = os.environ.get("STRUCTURE_ID")

SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_APP_PASSWORD = os.environ.get("SENDER_APP_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

def fetch_structures():
    headers = {'Authorization': f'Bearer {API_KEY}'}
    url = f'{BASE_URL}/api/v3/structures?page=0'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["values"]  # Return a list of structures
    else:
        # Handle errors (log them or throw an exception)
        return []

def fetch_sensors_for_structure(structure_id):
    headers = {
        'Authorization': f'Bearer {API_KEY}'
    }
    url = f'{BASE_URL}/api/v3/structures/{structure_id}'

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("sensors", [])
        else:
            print(f"Failed to fetch sensors for structure {structure_id}")
            return []
    except requests.RequestException as e:
        print(f"Error while fetching sensors for structure {structure_id}: {e}")
        return []

# Yhdistetään APIin ja pyritään saamaan response code 200, joka tarkoittaa, että sensori vastaa eli on verkossa
def is_sensor_online(eui, structure_id):
    headers = {
        'Authorization': f'Bearer {API_KEY}'
    }
    url = f'{BASE_URL}/api/v3/structures/{structure_id}/sensors/{eui}'

    try:
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()

            if 'online' in data and data['online'] is True:
                # Fetch the structure name
                structure_name = fetch_structures (structure_id)
                return True, structure_name
            else:
                return False, None
        else:
            return False, None

    except requests.RequestException as e:
        return False, None

def write_to_influxdb(eui, is_online, sensor_name, structure_name, structure_id):
    helsinki_timezone = pytz.timezone("Europe/Helsinki")
    helsinki_time = datetime.datetime.now(helsinki_timezone)
    point = Point("sensor_status").tag("eui", eui).tag("structure_id", structure_id).tag("structure_name", structure_name).field("is_online", is_online).time(helsinki_time)
    write_api.write(bucket=influxdb_bucket, record=point)

def update_sensor_status_in_firestore(eui, is_online, sensor_name, structure_name):
    sensor_doc = status_collection.document(eui)
    doc_snapshot = sensor_doc.get()

    if doc_snapshot.exists:
        data = doc_snapshot.to_dict()
        previous_status = data.get("is_online", None)

        update_data = {
            "is_online": is_online,
            "sensor_name": sensor_name,  # Include sensor name
            "structure_name": structure_name,  # Include structure name
            "last_updated": firestore.SERVER_TIMESTAMP
        }

        # Update 'last_status_change' only if there's a change in status
        if previous_status is None or previous_status != is_online:
            update_data["last_status_change"] = firestore.SERVER_TIMESTAMP

        sensor_doc.update(update_data)
    else:
        # If the document doesn't exist, create it with the current status and name
        sensor_doc.set({
            "is_online": is_online,
            "sensor_name": sensor_name,
            "structure_name": structure_name,
            "last_status_change": firestore.SERVER_TIMESTAMP,
            "last_updated": firestore.SERVER_TIMESTAMP
        })

def send_push_notification(sensor_eui, new_status, structure_name, sensor_name):
    message = f"Sensor '{sensor_name}' ({sensor_eui}) in '{structure_name}' is now {'online' if new_status else 'offline'}."

    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
    }

    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            print("Push notification sent successfully.")
        else:
            print("Failed to send push notification.")
    except requests.RequestException as e:
        print("Error while sending push notification:", e)

# Function to send email notifications (commented out for future use)
# def send_email_notification(subject, message):
#     try:
#         server = smtplib.SMTP('smtp.gmail.com', 587)
#         server.starttls()
#         server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
# 
#         msg = MIMEMultipart()
#         msg['From'] = SENDER_EMAIL
#         msg['To'] = RECEIVER_EMAIL
#         msg['Subject'] = subject
#         msg.attach(MIMEText(message, 'plain'))
# 
#         server.send_message(msg)
#         server.quit()
#         print("Email notification sent successfully.")
#     except Exception as e:
#         print(f"Error while sending email notification: {e}")

def check_sensor_status(request):
    structures = fetch_structures()

    for structure in structures:
        structure_id = structure["_id"]
        structure_name = structure["name"]
        sensors = fetch_sensors_for_structure(structure_id)

        for sensor in sensors:
            eui = sensor["eui"]
            sensor_name = sensor["userConfig"]["name"]  # Extract sensor name
            online_status = sensor["online"]

            # Retrieve the last known status from Firestore
            sensor_doc = status_collection.document(eui)
            doc_snapshot = sensor_doc.get()

            if doc_snapshot.exists:
                data = doc_snapshot.to_dict()
                previous_status = data.get("is_online", None)

                if previous_status is not None and online_status != previous_status:
                    send_push_notification(eui, online_status, structure_name, sensor_name)
                
                # email_subject = "Sensor Status Update"
                # email_message = "Your email message here..."
                # send_email_notification(email_subject, email_message)

                # Update sensor status based on the current status
                update_sensor_status_in_firestore(eui, online_status, sensor_name, structure_name)  # Corrected function call

                # Write to InfluxDB
                write_to_influxdb(eui, online_status, sensor_name, structure_name, structure_id)

    print("Sensor status checks completed.")

    return "Cloud Function executed successfully"