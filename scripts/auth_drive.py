from google_auth_oauthlib.flow import InstalledAppFlow
import os

# Define the scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def authenticate():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        print("token.json already exists. Delete it if you want to re-authenticate.")
        return

    if not os.path.exists('client_secret.json'):
        print("Error: client_secret.json not found. Please place it in this directory.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(
        'client_secret.json', SCOPES)
    
    # Run the local server flow
    # This will open a browser window for the user to log in
    creds = flow.run_local_server(port=0)
    
    # Save the credentials for the next run
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
    
    print("Authentication successful! token.json has been created.")

if __name__ == '__main__':
    authenticate()
