# GDrive Audit

GDrive-Audit is a permissions audit tool that traverses all the files in your business' Google Drive account and 
generates a spreadsheet displaying file permissions.  

## Install

Clone from repo, then:
```bash
> cd gdrive_audit
> python -m pip install --user virtualenv
> python -m venv venv
> source venv/bin/activate
> pip install -r requirements.txt
```

## Run

Open a local `python` interpreter and then run something like the following:

```python
from audit import GoogleDriveAuditReport
from audit import enable_stdout_logging

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

You must add your admin account as a Viewer to your team drives or the Drive API will not let you list contents.  This is not covered in this code.


## Credentials and Google API setup

Setting up your Google API credentials is non trivial, but this doc outlines the basic steps.

https://support.google.com/a/answer/7378726?hl=en


### Google Developer console

1. Login to https://console.cloud.google.com with the google account associated with your org.
2. Create a project.
3. Enable GDrive API and Admin SDK for the project.
4. Create a service account and set permission scope to `https://www.googleapis.com/auth/admin.directory.user.readonly, https://www.googleapis.com/auth/drive.readonly` and save.
4. Go to keys, add key, create new, json format **Save this - you'll need it!**
5. Copy the client ID (its an integer) of the service account, you'll need it to configure the admin.

### Google Admin

1. Login to https://admin.google.com with a super user account.
2. Go to Security > Access and data control > API controls > Manage third-party app access.
3. Configure new app > OAuth app name or client ID > Enter name of the app you created > Select > Select.
4. Enable domain-wide delegation under https://admin.google.com/u/1/ac/owl/domainwidedelegation adding the Client ID and the scopes.

### Run tests

```bash
$ python -m unittest
.........
----------------------------------------------------------------------
Ran 9 tests in 0.003s

OK
```

## TODO

Threading: the utility is currently a synchronous single-threaded application, so large drives can take a while.
We will convert this into a multi-threaded application at some point.
