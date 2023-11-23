import os
import datetime
from datetime import datetime
from google.cloud import firestore
import requests
# from email.mime.multipart import MIMEMultipart
# from email.mime.text import MIMEText

# Firestore client
db = firestore.Client()

# Define your Firestore collection reference for sensor status
status_collection = db.collection("sensors_grouped")

# Sender and Receiver Email Addresses (as a placeholder for future)
# SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
# SENDER_APP_PASSWORD = os.environ.get("SENDER_APP_PASSWORD")
# RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

# Pushover API and User Key
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")

def get_sensor_statuses():
    sensor_statuses = status_collection.stream()

    grouped_sensors = {}

    for sensor in sensor_statuses:
        data = sensor.to_dict()
        full_sensor_id = sensor.id
        # Extract only the last 6 characters of the sensor ID
        sensor_id = full_sensor_id[-6:]
        is_online = data.get("is_online", False)
        sensor_name = data.get("sensor_name", "Unknown Sensor")
        structure_name = data.get("structure_name", "Unknown Structure")
        last_status_change = data.get("last_status_change")

        status_message = f"{sensor_name} ({sensor_id}) - Lähtien {get_timestamp(last_status_change)}"

        if structure_name not in grouped_sensors:
            grouped_sensors[structure_name] = {"online": [], "offline": []}
        
        if is_online:
            grouped_sensors[structure_name]["online"].append(status_message)
        else:
            grouped_sensors[structure_name]["offline"].append(status_message)

    return grouped_sensors

def get_timestamp(last_change_time):
    if last_change_time:
        formatted_time = last_change_time.strftime("%m/%d/%Y %H:%M")
        return f"{formatted_time}"
    return "N/A"

def send_push_notification(message, html_format=False):
    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
    }

    if html_format:
        data["html"] = 1  # Enable HTML formatting

    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            print("Push notification sent successfully.")
        else:
            print("Failed to send push notification.", response.status_code)
    except requests.RequestException as e:
        error_message = f"Error while sending push notification: {e}"
        print(error_message)

#def send_email_notification(message):
#    # Set up the SMTP server
#    try:
#        server = smtplib.SMTP('smtp.gmail.com', 587)
#        server.starttls()
#        server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
#
#        # Create the email
#        msg = MIMEMultipart()
#        msg['From'] = SENDER_EMAIL
#        msg['To'] = RECEIVER_EMAIL
#        msg['Subject'] = "Aamun Sensorikooste"
#
#        # Attach the message
#        msg.attach(MIMEText(message, 'plain'))
#
#        # Send the email
#        server.send_message(msg)
#        server.quit()
#        print("Email notification sent successfully.")
#    except Exception as e:
#        print(f"Error while sending email notification: {e}")

def morning_summary(request):
    grouped_sensors = get_sensor_statuses()

    # Compose the message
    summary_message = "Aamun Sensorikooste:\n\n"  # Plain text for email
    for structure_name, sensors in grouped_sensors.items():
        if sensors["offline"]:
            summary_message += f"{structure_name} - Offline Sensorit:\n"
            summary_message += "\n".join(sensors["offline"]) + "\n\n"

        if sensors["online"]:
            summary_message += f"{structure_name} - Online Sensorit:\n"
            summary_message += "\n".join(sensors["online"]) + "\n\n"

    summary_message = summary_message.strip()

    # Send Pushover notification with HTML formatting
    send_push_notification(summary_message, html_format=True)

    # Send email notification (currently disabled)
    # send_email_notification(summary_message)

    return "Aamukoosteen Pushover-ilmoitus lähetetty."