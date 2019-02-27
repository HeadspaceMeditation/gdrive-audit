from external.types import NamedTupleFactory
import json
import os
import random
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from external.timeutils import iso_strptime
from google.oauth2 import service_account
from httplib2 import HttpLib2Error
from time import sleep
import logging
logger = logging.getLogger(__name__)


def generate_random_chars(length=6):
    upper_alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    random_code = "".join(random.choice(upper_alpha) for _ in xrange(length))
    return random_code


def random_credential_path():
    # Get random path to write credential to.
    credential_path = os.path.join(os.curdir, "credentials_" + generate_random_chars(25) + ".json")
    if os.path.exists(credential_path):
        return random_credential_path()
    return credential_path


class BackendConfigurationError(Exception):
    """
    Raised when an authentication or other config error occurs.
    Should not be retried.
    """
    pass


class RetryCountExceeded(Exception):
    """ Raised when max retries are exceeded after a transport error occurs. """
    pass


def execute_request(request, retry_count=0):
    try:
        return request.execute()
    except HttpError, e:
        # Http status error - look for auth problems.
        logger.exception("Failure: %s", e)
        raise BackendConfigurationError(e.message)
    except (HttpLib2Error, IOError):
        # Transport error - retry
        if retry_count > 10:
            raise RetryCountExceeded("Request failed after retry count exceeded", request=request)
        # Simple sleep before retry (designed for async worker with async sleep).
        sleep(1.0)
        return execute_request(request, retry_count=(retry_count + 1))


class GoogleAdminClient(object):
    """
    Google Admin API client wrapper.

    Convenience class for managing google api credentials and interacting with
    the google admin API.
    """
    gadmin_user_name = NamedTupleFactory("GAdminUserName", ["familyName", "givenName", "fullName"])
    gadmin_user = NamedTupleFactory("GAdminUser", ["agreedToTerms", "archived", "changePasswordAtNextLogin",
                                                   "creationTime", "customerId", "emails", "address", "etag", "id",
                                                   "includeInGlobalAddressList", "ipWhitelisted", "isAdmin",
                                                   "isDelegatedAdmin", "isEnforcedIn2Sv", "isEnrolledIn2Sv",
                                                   "isMailboxSetup", "kind", "lastLoginTime", "name", "orgUnitPath",
                                                   "primaryEmail", "suspended"], encoders={"name": gadmin_user_name})
    gadmin_user_list_response = NamedTupleFactory("GAdminUserListResponse", ["etag", "kind", "users", "nextPageToken"],
                                                  encoders={"users": gadmin_user})
    gdrive_user_reference = NamedTupleFactory("GDriveUserReference",
                                              ["kind", "displayName", "me", "permissionId", "emailAddress"])
    default_user_account = None
    credentials = None

    def __init__(self, credentials, connect_as=None, authorization_scope=None):
        """
        :type authorization_scope: list
        :param credentials: Dictionary representing Server2Server OAuth credentials (or json representation of dict).
        :param connect_as: Email address of proxy user whose permissions are to be emulated.
        :param authorization_scope: list of google authorization scopes.
        """
        if isinstance(credentials, basestring):
            credentials = json.loads(credentials)
        if not isinstance(credentials, dict):
            raise TypeError("Invalid credentials. Expected dictionary or json string represenation of dictionary.")

        # Google Service account credentials.
        self.credentials = credentials
        # Google API authorization scopes (types of api access required).
        self.authorization_scope = authorization_scope
        # Underlying google api client.
        self.client = None
        # User to use for permissions proxy (configured on connect).
        self.proxy_user = None
        # Credential file path.
        self.credential_path = None
        self.connect(connect_as)

    def _execute_request(self, request):
        """
        Execute the current request
        :param request:
        :return:
        """
        if not self.is_connected:
            self.connect(connect_as=self.proxy_user)
        return execute_request(request)

    @property
    def is_connected(self):
        return self.client and self.credential_path

    def close(self):
        """
        Clear existing credential state.
        Deleting credential file from disk (if present).
        """
        if self.credential_path and os.path.exists(self.credential_path):
            # Delete credentials file.
            os.remove(self.credential_path)
        self.credential_path = None
        self.client = None

    def connect(self, connect_as=None):
        """
        Configure the credential store and delegated user.
        :param connect_as:
        :return:
        """
        self.load_credentials(connect_as)

        # Setup the Google admin client
        self.authorization_scope = self.authorization_scope or \
                                   ['https://www.googleapis.com/auth/admin.directory.user.readonly',
                                    'https://www.googleapis.com/auth/drive.readonly']
        credentials = service_account.Credentials.from_service_account_file(
            self.credential_path, scopes=self.authorization_scope)

        if not self.proxy_user:
            self.client = build('admin', 'directory_v1', credentials=credentials)
            return

        self.client = build('admin', 'directory_v1', credentials=(credentials.with_subject(self.proxy_user)))

    def load_credentials(self, connect_as):
        """
        Prepare credentials for connection.
        :param connect_as:
        :return:
        """
        if self.is_connected:
            self.close()

        if not connect_as:
            # Connect as last configured user account or if not provided, default user account.
            connect_as = self.proxy_user or self.default_user_account

        # Write credentials to file.
        self.proxy_user = connect_as
        self.credential_path = random_credential_path()
        f = open(self.credential_path, 'wb')
        f.write(json.dumps(self.credentials).encode('utf-8'))
        f.close()

    def all_users(self, page_token=None, previous_pages=None):
        """
        Get all uses associated with the current customer account.
        :param page_token:
        :param previous_pages:
        :return:
        """
        # Specify all users for the customer ID associated with credentials.
        params = dict(customer="my_customer")
        if page_token:
            # Continue a previously run paginated query result.
            params["pageToken"] = page_token

        request = self.client.users().list(**params)
        user_list_response = self.gadmin_user_list_response.from_python(self._execute_request(request))
        all_files = user_list_response.users or []

        if previous_pages:
            # Combine current and previous pages of results.
            all_files = previous_pages + all_files

        if user_list_response.nextPageToken:
            # More pages available, recurse and fetch next page.
            return self.all_users(page_token=user_list_response.nextPageToken,
                                  previous_pages=all_files)

        return all_files


class GoogleDriveClient(GoogleAdminClient):
    """
    GoogleDrive api client wrapper.

    Convenience class for managing google api credentials and interacting with
    the Google Drive API.
    """
    gdrive_team_drive_permission = NamedTupleFactory("GDriveTeamDrivePermission",
                                                     ["teamDrivePermissionType", "role", "inheritedFrom", "inherited"])
    gdrive_file_permission = NamedTupleFactory("GDriveFilePermission",
                                               ["kind", "id", "type", "emailAddress", "domain", "role",
                                                "allowFileDiscovery", "displayName", "expirationTime",
                                                "teamDrivePermissionDetails", "deleted"],
                                               encoders={"teamDrivePermissionDetails": gdrive_team_drive_permission})
    gdrive_file = NamedTupleFactory("GDriveFile",
                                    ["kind", "id", "name", "mimeType", "starred", "trashed",
                                     "explicitlyTrashed", "parents", "version", "webContentLink",
                                     "webViewLink", "iconLink", "hasThumbnail", "viewedByMe",
                                     "viewedByMeTime", "createdTime", "modifiedTime", "modifiedByMeTime",
                                     "modifiedByMe", "owners", "lastModifyingUser", "shared",
                                     "ownedByMe", "capabilities", "viewersCanCopyContent", "writersCanShare",
                                     "permissions", "originalFilename", "fullFileExtension",
                                     "fileExtension", "md5Checksum", "size", "headRevisionId"],
                                    encoders={"owners": GoogleAdminClient.gdrive_user_reference,
                                              "lastModifyingUser": GoogleAdminClient.gdrive_user_reference,
                                              "permissions": gdrive_file_permission},
                                    decoders={"createdTime": iso_strptime, "modifiedTime": iso_strptime}
                                    )

    gdrive_file_list = NamedTupleFactory("GDriveFileList", ["files", "nextPageToken", "incompleteSearch", "kind"],
                                         encoders={"files": gdrive_file})
    folder_mime_type = 'application/vnd.google-apps.folder'
    gdrive_restrictions = NamedTupleFactory("GDriveRestrictions",
                                            ["adminManagedRestrictions", "copyRequiresWriterPermission",
                                             "domainUsersOnly", "teamMembersOnly"])
    gdrive_team_drive = NamedTupleFactory("GDriveTeamDrive",
                                          ["kind", "id", "name", "createdTime", "restrictions"],
                                          encoders={"restrictions": gdrive_restrictions})
    gdrive_team_drive_response = NamedTupleFactory("GDriveTeamDriveList",
                                                   ["kind", "nextPageToken", "teamDrives"],
                                                   encoders={"teamDrives": gdrive_team_drive})

    def connect(self, connect_as=None):
        """
        Configure the credential store and delegated user.
        :param connect_as:
        :return:
        """
        self.load_credentials(connect_as=connect_as)

        # Setup the GDrive Client
        self.authorization_scope = self.authorization_scope or \
                                   ['https://www.googleapis.com/auth/drive.readonly']
        credentials = service_account.Credentials.from_service_account_file(
            self.credential_path, scopes=self.authorization_scope)
        if not self.proxy_user:
            self.client = build('drive', 'v3', credentials=credentials)
            return
        self.client = build('drive', 'v3', credentials=(credentials.with_subject(self.proxy_user)))

    def walk_tree(self, folder_id='root', path=None, depth=0, max_depth=20, my_folders_only=True,
                  exclude_folders_named=None):
        """
        Given a folder_id, iterate through all subfolders and return file data.

        :param folder_id: ID of folder to walk down from.
        :param path: name of current folder (used in recursion)
        :param depth: current depth (used in recursion)
        :param max_depth: max depth to descend (prevents infinite loops)
        :param my_folders_only: only walk folders that I own
        :param exclude_folders_named: list of folder names which should be skipped if encountered.
        :return:
        """
        all_files = []
        folders = []
        if exclude_folders_named and not isinstance(exclude_folders_named, (list, tuple, set)):
            raise ValueError("Parameter exclude_folders_named must be a list, tuple or set type containing "
                             "folder names to exclude.")
        exclude_folders_named = set(exclude_folders_named or [])

        if not path:
            path = folder_id

        logger.info("Walking folder hierarchy %s: %s.", self.proxy_user, path)

        file_entries = self.files(folder_id=folder_id)
        if not file_entries:
            return all_files

        for fe in file_entries:
            if fe.mimeType == self.folder_mime_type:
                folders.append(fe)
            else:
                all_files.append([path, fe])

        def owner_is_me(folder_obj):
            for usr in folder_obj.owners:
                if usr.me:
                    return True
            return False

        for folder in folders:

            if my_folders_only and not owner_is_me(folder):
                # Only walk folders that I own.
                logger.info("Skipping folder '%s/%s' not owned by %s.", path, folder.name, self.proxy_user)
                continue

            if exclude_folders_named and folder.name in exclude_folders_named:
                # Do not walk folders named as described.
                logger.info("Skipping excluded folder named '%s' at path '%s'.", folder.name, path)
                continue

            if depth >= max_depth:
                logger.warning("Max depth exceeded while auditing gdrive for %s.", self.proxy_user)
                continue

            file_entries = self.walk_tree(folder_id=folder.id,
                                          depth=depth + 1,
                                          path=path + "/" + folder.name,
                                          max_depth=max_depth,
                                          exclude_folders_named=exclude_folders_named)
            if not file_entries:
                continue

            all_files.extend(file_entries)

        return all_files

    def files(self, folder_id=None, after=None, before=None, page_token=None, previous_pages=None):
        """
        Get all files matching the search parameters.

        Note: this will page through all matching files result set is complete.

        :param folder_id: just files in this folder (if blank, files owned by current proxy user will be returned)
        :param after: (optional) beginning last modified date range
        :param before: (optional) ending last modified date range
        :param page_token: leave empty - only used when recursing paged results
        :param previous_pages: leave empty - only used when recursing paged results
        :return: an array of gdrive_file_reference objects found in the described folder
        """
        # Primary operation here is to list all files and folders visible to the specified user.
        if not page_token:
            q = "trashed = false"
            if after:
                # Add a beginning date range to the query.
                q = "modifiedTime > '{after}' and {q}".format(q=q, after=after.isoformat())
            if before:
                # Add an ending date range to the query.
                q = "modifiedTime < '{before}' and {q}".format(q=q, before=before.isoformat())

            if folder_id:
                # Restrict files to the following containing folder(s).
                if isinstance(folder_id, basestring):
                    q = "'{folder_id}' in parents and {q}".format(folder_id=folder_id, q=q)
                elif isinstance(folder_id, (list, tuple)):
                    q = "(" + \
                        " or ".join("'{folder_id}' in parents".format(folder_id=f) for f in folder_id) + \
                        ") and {q}".format(q=q)
                params = dict(includeTeamDriveItems=True, supportsTeamDrives=True,
                              fields="files,nextPageToken,incompleteSearch,kind", q=q)
            else:
                # Restrict files by owner.
                q = "'{owner}' in owners and {q}".format(owner=self.proxy_user, q=q)
                params = dict(includeTeamDriveItems=False, supportsTeamDrives=False,
                              fields="files,nextPageToken,incompleteSearch,kind", q=q)

        else:
            # Continue a previously run paginated query result.
            logger.info("Paging request... ")
            params = dict(pageToken=page_token)

        request = self.client.files().list(**params)
        try:
            file_list_response = self.gdrive_file_list.from_python(self._execute_request(request))
        except BackendConfigurationError:
            logger.exception("An error occurred while listing gdrive files.")
            return previous_pages or []

        all_files = file_list_response.files or []
        logger.info("List files request retrieved %s files." % len(all_files))

        if previous_pages:
            # Combine current and previous pages of results.
            all_files = previous_pages + all_files

        if file_list_response.incompleteSearch:
            # More pages available, recurse and fetch next page.
            return self.files(page_token=file_list_response.nextPageToken,
                              previous_pages=all_files)
        return all_files

    def team_drives(self, page_token=None, previous_pages=None):
        """
        Get a list of all team drives in the account.
        Note: recurses through paginated results until all drives can be returned.

        :param page_token: (for recursion only)
        :param previous_pages: (for recursion only)
        :return: list of gdrive_team_drive objects
        """
        if not previous_pages:
            previous_pages = []

        if not page_token:
            params = {
                "pageSize": 100,
                "useDomainAdminAccess": True,
            }
        else:
            # Continue a previously run paginated query result.
            params = dict(pageToken=page_token)

        try:
            request = self.client.teamdrives().list(**params)
            response = self._execute_request(request)
        except:
            logger.exception("Failed to retrieve team drive list.")
            return None

        response = self.gdrive_team_drive_response.from_python(response)
        if response.teamDrives:
            team_drives = previous_pages + response.teamDrives
        else:
            team_drives = previous_pages

        if not response.nextPageToken:
            return team_drives

        return self.team_drives(page_token=response.nextPageToken, previous_pages=team_drives)
