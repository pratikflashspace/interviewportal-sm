"""Run locally on the Drive owner's computer, NEVER on the public web server.

pip install -r tools/drive-setup-requirements.txt
python tools/connect_personal_drive.py --client /private/path/client.json --output /private/path/render-drive.env

Creates an app-owned folder in personal My Drive under drive.file scope. Existing
folder URLs alone do not grant drive.file authorization. No all-Drive scope.
Credentials go to a new private local file, never stdout or repository files.
"""
import argparse
import json
import os
from pathlib import Path

SCOPE='https://www.googleapis.com/auth/drive.file'
FOLDER_NAME='Flashspace Interview Recordings - Staging'


def secure_destination(path):
    path=Path(path).expanduser().resolve()
    repo=Path(__file__).resolve().parents[2]
    if path==repo or repo in path.parents:
        raise ValueError('Choose an output file outside the repository.')
    if path.exists():raise ValueError('Output already exists; choose a new private file.')
    if not path.parent.is_dir():raise ValueError('Output directory must already exist.')
    return path


def main():
    parser=argparse.ArgumentParser(description='Authorize personal Drive without sharing credentials in chat.')
    parser.add_argument('--client',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    destination=secure_destination(args.output)
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import AuthorizedSession
    config=json.loads(Path(args.client).expanduser().read_text())
    if 'installed' not in config:
        raise ValueError('Use a Desktop app OAuth client for this local setup utility.')
    flow=InstalledAppFlow.from_client_config(config,[SCOPE])
    creds=flow.run_local_server(host='localhost',port=0,open_browser=True,
        authorization_prompt_message='Opening Google sign-in. Choose the account that will own interview recordings.',
        success_message='Drive authorization received. You can close this tab.',
        access_type='offline',prompt='consent')
    if not creds.refresh_token:raise RuntimeError('No refresh token returned; authorization is incomplete.')
    session=AuthorizedSession(creds)
    # No existing personal files are listed or touched. Google grants drive.file
    # access to this newly created folder and files created by this app.
    response=session.post('https://www.googleapis.com/drive/v3/files',
        params={'fields':'id,webViewLink'},json={'name':FOLDER_NAME,'mimeType':'application/vnd.google-apps.folder'},timeout=30)
    if response.status_code!=200:raise RuntimeError('Folder creation failed. Check Drive API enablement and account storage.')
    folder=response.json()
    if not isinstance(folder.get('id'),str):raise RuntimeError('Folder creation returned invalid metadata.')
    values={'GOOGLE_DRIVE_CLIENT_ID':creds.client_id,'GOOGLE_DRIVE_CLIENT_SECRET':creds.client_secret,
            'GOOGLE_DRIVE_REFRESH_TOKEN':creds.refresh_token,'GOOGLE_DRIVE_FOLDER_ID':folder['id']}
    # JSON-quoted dotenv values: enter decoded values without surrounding quotes
    # in individual Render environment fields. Keep the file out of chat/screenshots.
    content='\n'.join(k+'='+json.dumps(v) for k,v in values.items())+'\n'
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(content)
    print('Authorization completed. Secret settings were written to your requested private local file.')
    print('A new restricted staging recordings folder was created in your My Drive.')
    print('Enter the four settings securely in Render. Do not share the file, values or token in chat.')
    print('Testing-mode Google OAuth refresh tokens can expire after seven days. This is not a production authorization guarantee.')


if __name__=='__main__':
    try:main()
    except Exception:
        # OAuth exceptions may include sensitive URL/response details.
        print('Setup did not complete. Verify the Desktop OAuth client, Drive API, test-user account and private output path. No credential details printed.')
        raise SystemExit(1)
