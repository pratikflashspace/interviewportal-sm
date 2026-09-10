"""Private personal-Drive adapter, not yet exposed as a candidate upload route.

OAuth credentials must be supplied by the owner through secure server settings.
No public permission creation; no delete API until retention is approved.
The caller must bind ownership, persist upload_session and file_id securely, and
validate candidate content/size before calling this adapter. Upload-session URLs
are bearer secrets and must never be logged or placed in ClickUp.
"""
import io
import os
import re

SCOPE='https://www.googleapis.com/auth/drive.file'
MAX_BYTES=500*1024*1024

class DriveError(RuntimeError):pass


def build_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    names=('GOOGLE_DRIVE_CLIENT_ID','GOOGLE_DRIVE_CLIENT_SECRET','GOOGLE_DRIVE_REFRESH_TOKEN')
    values=[os.getenv(k,'').strip() for k in names]
    if not all(values):raise DriveError('Configure the owner-authorized Drive credentials securely.')
    creds=Credentials(token=None,refresh_token=values[2],token_uri='https://oauth2.googleapis.com/token',
        client_id=values[0],client_secret=values[1],scopes=[SCOPE])
    return build('drive','v3',credentials=creds,cache_discovery=False)


class PersonalDrive:
    def __init__(self,service=None,folder=None):
        self.folder=folder or os.getenv('GOOGLE_DRIVE_FOLDER_ID','').strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',self.folder):raise DriveError('Configure the app-authorized recording folder.')
        self.service=service if service is not None else build_service()

    def validate_destination(self):
        try:
            result=self.service.files().get(fileId=self.folder,fields='id,mimeType,trashed,capabilities(canAddChildren)').execute(num_retries=0)
            if result.get('trashed') or result.get('mimeType')!='application/vnd.google-apps.folder' or not result.get('capabilities',{}).get('canAddChildren'):
                raise DriveError('The configured folder is not writable.')
            permissions=self.service.permissions().list(fileId=self.folder,fields='permissions(type,role)',pageSize=100).execute(num_retries=0)
            if any(p.get('type') in ('anyone','domain') for p in permissions.get('permissions',[])):
                raise DriveError('Recording folder must not have public or domain-wide sharing.')
            return True
        except DriveError:raise
        except Exception:raise DriveError('Could not verify recording folder access.') from None

    def allocate(self,recording_id):
        # Preallocate and persist this ID before an upload, so retries use update
        # on a known identity rather than duplicate creates after a timeout.
        if not re.fullmatch(r'[a-f0-9-]{32,36}',recording_id):raise DriveError('Invalid recording identity.')
        try:return self.service.files().generateIds(count=1,space='drive',type='files').execute(num_retries=0)['ids'][0]
        except Exception:raise DriveError('Unable to allocate a recording file identity.') from None

    def initialize_file(self,file_id,recording_id):
        if not re.fullmatch(r'[a-f0-9-]{32,36}',recording_id):raise DriveError('Invalid recording identity.')
        self.validate_destination()
        try:
            return self.service.files().create(body={'id':file_id,'name':'Interview-'+recording_id+'.webm',
                'parents':[self.folder],'mimeType':'video/webm','appProperties':{'recording_id':recording_id}},
                fields='id,webViewLink').execute(num_retries=0)
        except Exception:
            # Ambiguous create may already have succeeded. Reconcile exact ID,
            # parent and app recording identity before accepting the result.
            try:
                found=self.service.files().get(fileId=file_id,fields='id,parents,appProperties,trashed,webViewLink').execute(num_retries=0)
                if not found.get('trashed') and self.folder in found.get('parents',[]) and found.get('appProperties',{}).get('recording_id')==recording_id:return found
            except Exception:pass
            raise DriveError('Could not initialize the recording file; reconcile before retrying.') from None

    def upload_request(self,file_id,stream,size):
        if type(size) is not int or not 1<=size<=MAX_BYTES:raise DriveError('Recording exceeds the pilot size limit.')
        if not hasattr(stream,'read') or not hasattr(stream,'seek'):raise DriveError('Upload requires a seekable staged stream.')
        from googleapiclient.http import MediaIoBaseUpload
        media=MediaIoBaseUpload(stream,mimetype='video/webm',chunksize=1024*1024,resumable=True)
        if media.size()!=size:raise DriveError('Recording size does not match its manifest.')
        return self.service.files().update(fileId=file_id,media_body=media,fields='id,size,webViewLink')

    @staticmethod
    def next_chunk(upload):
        try:return upload.next_chunk(num_retries=2)
        except Exception:raise DriveError('Recording upload interrupted. Retain the staged bytes and resume this upload session.') from None
