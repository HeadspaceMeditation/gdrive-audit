# GDrive Audit

GDrive-Audit is a permissions audit tool that traverses all the files in your business' Google Drive account and 
generates a spreadsheet displaying file permissions.  

## Install
Clone from repo, then:
```
> cd gdrive_audit
> pip install -r requirements.txt
```

## Run
```
from gdrive_audit.audit import GoogleDriveAuditReport
from gdrive_audit.audit import enable_stdout_logging

# Optionally, enable logging to stdout.
enable_stdout_logging()

# Create a report instance and start it:  
report = GoogleDriveAuditReport('google_service_acct_credentials.json', 
                                'admin_user@yourdomain.com')    
report.start(output_file_name='my_audit_report.csv')

# Wait for it... (It can take a while to traverse all user directories.)
```
## User drives
GDrive-Audit uses a service account and the Google Admin and Drive APIs to traverse all user folders.
Once all user folders are traversed, it exports a spreadsheet of all files and permissions for every user's drive 
within your customer account.

## Team drives
Team drive support has not been fully implemented- feel free to create a pull request!


## Credentials and Google API setup
Setting up your Google API credentials is non trivial, but this doc outlines the basic steps.

https://support.google.com/a/answer/7378726?hl=en


### Google Developer console
1. Login to https:/console.developers.google.com with the google account associated with your org.
2. Create a project.
3. Enable GDrive API and Admin SDK for the project.
4. Create service account credentials and download the private key in json format **Save this - you'll need it!**
5. Enable G Suite Domain-wide delegation for the service account.
6. Copy the client ID (its an integer) of the service account, you'll need it to configure the admin.

### Google Admin
1. Login to https://admin.google.com with a super user account.
3. Go to Security > Advanced Settings > Manage API client access
4. Under client name, enter the client ID from above, then set permission scope to `https://www.googleapis.com/auth/admin.directory.user.readonly, https://www.googleapis.com/auth/drive.readonly` and save.


## TODO
Threading: the utility is currently a synchronous single-threaded application, so large drives can take a while.
We will convert this into a multi-threaded application at some point.
