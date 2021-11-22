from clients import GoogleAdminClient, GoogleDriveClient
from external import csv_utils
from datetime import datetime
import logging
import sys
import json
import time
from logging import Handler

logger = logging.getLogger(__name__)

def _dt_fmt(dt):
    if not isinstance(dt, datetime):
        return dt
    return dt.strftime("%Y-%m-%d")


def enable_stdout_logging():
    """
    Invoke this prior to starting report to enable stdout logging.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)


class GoogleDriveAuditReport(object):
    """
    Reporting utility that generates a local spreadsheet of GDrive files and permissions.
    Usage is simple but the utility can take a while to run, see example usage below:
    """

    def __init__(self, credentials, admin_user, audit_users=True, audit_team_drives=False):
        self.should_audit_users = audit_users
        self.should_audit_drives = audit_team_drives

        if not isinstance(credentials, str):
            raise ValueError("'credentials' must be a json formatted credential string, "
                             "or a filename pointing to a json formatted credential string.")

        try:
            credentials = json.loads(credentials)
        except:
            # This is probably a filename and not a json formatted string.
            # Error will be raised if it is not a valid file path.
            f = open(credentials, "rb")
            credentials = f.read().decode('utf-8')
            f.close()

        if not admin_user:
            raise ValueError('admin_user must be supplied (Google email address of user with administrative rights.')

        self.credentials = credentials
        self.user_files = dict()
        self.team_drive_files = dict()
        self.admin_user = admin_user

        # By default .git folders are ignored.
        # To add exclusion folders, set this property before starting the report.
        self.exclude_folders_named = [".git"]

    def start(self, output_file_name=None):
        """
        Start generating the report.
        :return:
        """
        self.audit_users()
        self.audit_team_drives()

        if self.should_audit_users:
            self.export_user_drive_report(output_file_name)

        if self.should_audit_drives:
            self.export_team_drive_report()

    def audit_team_drives(self):
        """
        Audit all files found within team drives.
        Team drives audit is untested - we don't have an team drive enabled account to test on.
        :return:
        """
        if not self.should_audit_drives:
            logger.info("Skipping audit of team drives.")
            return

        logger.info("Beginning google drive audit of team drives.")

        # When `useDomainAdminAccess` is set to True, you must connect as your admin user or it will *not* work.
        drive_client = GoogleDriveClient(self.credentials,
                                         connect_as=self.admin_user)
        folders = drive_client.team_drives()
        for folder in folders:
            files = None
            try:
                files = drive_client.walk_tree(folder_id=folder.id,
                                               team_drive_id=folder.id,
                                               path=folder.name,
                                               max_depth=30,
                                               my_folders_only=False,
                                               exclude_folders_named=self.exclude_folders_named,
                                               team_drive=True)
                if not files:
                    logger.info("No files found in team drive %s.", folder.name)

                self.team_drive_files[folder.name] = files
                logger.info("Completed audit of team drive %s. %i files found.", folder.name, len(files))
            except:
                logger.exception("Error occurred querying drive files for team drive %s.", folder.name)

        drive_client.close()

    def audit_users(self):
        """
        Audit all files found in user drives.
        :return:
        """
        if not self.should_audit_users:
            logger.info("Skipping audit of user drives.")
            return

        logger.info("Beginning google drive audit of user drives.")
        users = self.get_users()

        if not users:
            return

        for user in users:
            if not user.primaryEmail:
                continue
            files = self.list_user_drive(user)
            if not files:
                logger.info("No files found in user drive %s.", user.primaryEmail)
                continue

            logger.info("Completed audit of user drive %s. %i files found.", user.primaryEmail, len(files))
            self.user_files[user.primaryEmail] = files

    def list_user_drive(self, user):
        """
        Connect as the specified user and get report on all files.
        """
        drive_client = None
        files = None
        try:
            drive_client = GoogleDriveClient(self.credentials,
                                             connect_as=user.primaryEmail)
            files = drive_client.walk_tree(exclude_folders_named=self.exclude_folders_named)

        except:
            logger.exception("Error occurred querying drive files for user %s.", user.primaryEmail)

        finally:
            if drive_client:
                drive_client.close()
        return files

    def get_users(self):
        """
        Call the admin api and get a list of all user objects.
        :return:
        """
        admin_client = None
        users = None
        try:
            admin_client = GoogleAdminClient(self.credentials, connect_as=self.admin_user)
            users = admin_client.all_users()
        except:
            logger.exception("Error occurred querying google users.")
        finally:
            if admin_client:
                admin_client.close()
        return users

    def export_user_drive_report(self, output_file_name=None):
        """
        Export a csv file of the user drive permission report.
        :return:
        """
        if not self.user_files:
            return None

        rows = []
        for email, file_data in self.user_files.items():
            for path, f in file_data:
                row = {"User Drive": email, "path": path, "name": f.name, "mimeType": f.mimeType,
                       "trashed": f.trashed, "webViewLink": f.webViewLink,
                       "createdTime": _dt_fmt(f.createdTime), "modifiedTime": _dt_fmt(f.modifiedTime),
                       "owners": self.file_owners(f),
                       "lastModifyingUser": self.file_last_modified_by(f), "shared": f.shared,
                       "viewersCanCopy": f.viewersCanCopyContent,
                       "usersAndGroups": self.user_permission_string(f.permissions),
                       "domains": self.domain_permission_string(f.permissions),
                       "anyone": self.anyone_permission_string(f.permissions)
                       }
                rows.append(row)

        out = csv_utils.records_to_string(rows)
        if not output_file_name:
            timestamp = time.mktime(datetime.now().timetuple())
            output_file_name = "user_permission_report_%i.csv" % timestamp

        logger.info("Writing user drive permissions report to '%s.'" % output_file_name)
        f = open(output_file_name, "wb")
        f.write(out.encode('utf-8'))
        f.close()
        logger.info("Finished.")

    @staticmethod
    def file_owners(file_obj):
        if not file_obj.owners:
            return ""
        owner_emails = [o.emailAddress for o in file_obj.owners if isinstance(o.emailAddress, str)]
        return ",".join(owner_emails)

    @staticmethod
    def file_last_modified_by(file_obj):
        if not file_obj.lastModifyingUser:
            return None
        return file_obj.lastModifyingUser.emailAddress

    @staticmethod
    def user_permission_string(permissions):
        if not permissions:
            return ""
        user_permissions = (p for p in permissions if p.type in {'user', 'group'} and not p.deleted)
        return ",".join("{}:{}:{}".format(p.type, p.emailAddress, p.role)
                        for p in user_permissions)

    @staticmethod
    def domain_permission_string(permissions):
        if not permissions:
            return ""
        domain_permissions = (p for p in permissions if p.type == 'domain' and not p.deleted)
        return ",".join("{}:{}:D({})".format(p.domain, p.role, p.allowFileDiscovery)
                        for p in domain_permissions)

    @staticmethod
    def anyone_permission_string(permissions):
        if not permissions:
            return ""
        public_permissions = (p for p in permissions if p.type == 'anyone' and not p.deleted)
        return ",".join("{}:D({})".format(p.role, p.allowFileDiscovery)
                        for p in public_permissions)

    def export_team_drive_report(self, output_file_name=None):
        """
        Export a csv file of the team drive permission report.
        :return:
        """
        if not self.team_drive_files:
            return None

        rows = []
        for email, file_data in self.team_drive_files.items():
            for path, f in file_data:
                row = {"Shared Drive": email, "path": path, "name": f.name, "mimeType": f.mimeType,
                       "trashed": f.trashed, "webViewLink": f.webViewLink,
                       "createdTime": _dt_fmt(f.createdTime), "modifiedTime": _dt_fmt(f.modifiedTime),
                       "owners": self.file_owners(f),
                       "lastModifyingUser": self.file_last_modified_by(f), "shared": f.shared,
                       "viewersCanCopy": f.viewersCanCopyContent,
                       "usersAndGroups": self.user_permission_string(f.permissions),
                       "domains": self.domain_permission_string(f.permissions),
                       "anyone": self.anyone_permission_string(f.permissions)
                       }
                rows.append(row)

        out = csv_utils.records_to_string(rows)
        if not output_file_name:
            timestamp = time.mktime(datetime.now().timetuple())
            output_file_name = "team_permission_report_%i.csv" % timestamp

        logger.info("Writing team drive permissions report to '%s.'" % output_file_name)
        f = open(output_file_name, "wb")
        f.write(out.encode('utf-8'))
        f.close()
        logger.info("Finished.")
