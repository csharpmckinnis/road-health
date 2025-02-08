#box_watcher.py
import requests
from logging_config import logger
from box_sdk_gen import BoxClient, BoxDeveloperTokenAuth, BoxCCGAuth, CCGConfig, UploadFileAttributes, UploadFileAttributesParentField, CreateCollaborationItem, CreateCollaborationItemTypeField, CreateCollaborationAccessibleBy, CreateCollaborationAccessibleByTypeField, CreateCollaborationRole
from boxsdk.config import API
import os
from dotenv import load_dotenv
import json
import base64
import hashlib
import io
import datetime
from utils import unprocessed_videos_path


# Load environment variables from .env file
load_dotenv()

# Access the Box credentials
BOX_DEV_TOKEN = os.getenv("BOX_DEV_TOKEN")
BOX_CLIENT_ID = os.getenv("BOX_CLIENT_ID")
BOX_CLIENT_SECRET = os.getenv("BOX_CLIENT_SECRET")
BOX_ENTERPRISE_ID = os.getenv("BOX_ENTERPRISE_ID")

class Box():
    def __init__(self, client_id=None, client_secret=None, enterprise_id=None):
        self.client_id = client_id or BOX_CLIENT_ID
        self.client_secret = client_secret or BOX_CLIENT_SECRET
        self.enterprise_id = enterprise_id or BOX_ENTERPRISE_ID
        self.client = None
        self.auth = None
        self.videos_folder_box_id = None
        self.unprocessed_videos_folder = unprocessed_videos_path

        self.authenticate()
        print(f"{self.client = }")
        box_items = self.list_items_in_folder('0')
        videos_folder_id = next(item for item in box_items if item['name'] == 'Videos')['id']
        self.videos_folder_box_id = videos_folder_id




    ## SECURITY AND AUTHENTICATION

    def authenticate(self):
        """
        Authenticates the client using the Client Credentials Grant (CCG) flow.
        """
        try:
            # Set up CCG-based authentication
            ccg_config = CCGConfig(
                client_id=self.client_id,
                client_secret=self.client_secret,
                enterprise_id=self.enterprise_id
            )
            self.auth = BoxCCGAuth(config=ccg_config)
            self.client = BoxClient(auth=self.auth)
            logger.info("Authentication successful. BoxClient initialized.")
        except Exception as e:
            logger.exception(f"Authentication failed: {e}")
            raise
        
    def test_connection(self):
        """
        Tests the connection by retrieving items from the root folder.
        """
        try:
            root_folder = self.client.folders.get_folder_by_id('0')
            logger.info(f"Connected to Box as: {self.client}")
            logger.info(f"Root folder name: {root_folder.name}")
            logger.info("Listing items in the root folder:")

            # Retrieve and log items in the root folder
            for item in root_folder.item_collection.entries:
                logger.info(f"- {item.type.capitalize()} | Name: {item.name} | ID: {item.id}")
        except Exception as e:
            logger.error(f"Error testing connection: {e}")

    def create_videos_folder(self, parent_folder_id='0'):
        """
        Checks if a folder named 'Videos' exists under the specified parent folder.
        If not, creates the folder and returns its ID.

        Args:
            parent_folder_id (str): The ID of the parent folder. Default is '0' (root folder).

        Returns:
            str: The ID of the 'Videos' folder.
        """
        folder_name = "Videos"
        try:
            # Check if the folder already exists
            folder_id = self.get_folder_id_by_name(folder_name, parent_folder_id)
            if folder_id:
                logger.info(f"Folder '{folder_name}' already exists with ID: {folder_id}")
                return folder_id
            else:
                logger.info(f"Folder '{folder_name}' does not exist. Creating...")
                folder_id = self.create_folder(folder_name, parent_folder_id)
                if folder_id:
                    return folder_id
                else:
                    logger.error(f"Failed to create folder '{folder_name}'.")
                    return None
        except Exception as e:
            logger.error(f"Error creating 'Videos' folder: {e}")
            return None
        
    def create_folder(self, folder_name, parent_folder_id='0'):
        """
        Creates a folder under the specified parent folder.
        """
        try:
            parent_folder = self.client.folders.get_folder_by_id(folder_id=parent_folder_id)
            new_folder = self.client.folders.create_folder(folder_name, parent_folder)
            logger.info(f"Folder '{folder_name}' created with ID: {new_folder.id}")
            return new_folder.id
        except Exception as e:
            logger.error(f"Error creating folder '{folder_name}': {e}")
            return None

    def get_folder_id_by_name(self, folder_name, parent_folder_id='0'):
        """
        Retrieves the folder ID for a given folder name under the specified parent folder.
        """
        try:
            parent_folder = self.client.folders.get_folder_by_id(folder_id=parent_folder_id)
            items = parent_folder.item_collection.entries
            for item in items:
                if item.name == folder_name and item.type == 'FolderBaseTypeField':
                    logger.info(f"Folder '{folder_name}' found with ID: {item.id}")
                    return item.id
            logger.warning(f"Folder '{folder_name}' not found under parent folder '{parent_folder_id}'.")
            return None
        except Exception as e:
            logger.error(f"Error retrieving folder ID: {e}")
            return None
        
    def list_items_in_folder(self, folder_id):
        """
        Lists all items in the specified folder.
        Args:
            folder_id (str): The ID of the folder to retrieve items from.
        Returns:
            list: A list of item details (name and ID) in the folder.
        """
        try:
            # Retrieve the folder and its items
            folder = self.client.folders.get_folder_by_id(folder_id)
            items = folder.item_collection.entries

            # Log and print the items in the folder
            item_list = []
            for item in items:
                item_list.append({"name": item.name, "id": item.id})
            return item_list
        except Exception as e:
            logger.error(f"Failed to list items in folder '{folder_id}': {e}")
            return []

    def upload_small_file_to_folder(self, file_path, folder_id):
        """
        Uploads a <50MB file to the specified folder.
        Args:
            file_path (str): The local path to the file to upload.
            folder_id (str): The ID of the folder to upload to.
        Returns:
            dict: Information about the uploaded file.
        """
        try:
            # Open the file and prepare a byte stream
            with open(file_path, "rb") as file:
                file_name = os.path.basename(file_path)

                # Set up the file attributes for the upload
                attributes = UploadFileAttributes(
                    name=file_name,
                    parent=UploadFileAttributesParentField(id=folder_id),
                )

                # Perform the upload
                uploaded_file = self.client.uploads.upload_file(attributes, file)
                logger.info(f"File '{file_name}' uploaded successfully with ID: {uploaded_file.id}")
                return uploaded_file
        except Exception as e:
            logger.error(f"Failed to upload file '{file_path}': {e}")
            return None
    
    def upload_large_file_to_box(self, file_path, file_name, parent_folder_id):
        """Uploads a large file using the Box Gen SDK's `upload_big_file()` method."""
        
        file_size = os.path.getsize(file_path)

        try:
            with open(file_path, 'rb') as file_stream:
                uploaded_file = self.client.chunked_uploads.upload_big_file(
                    file=file_stream,
                    file_name=file_name,
                    file_size=file_size,
                    parent_folder_id=parent_folder_id
                )

            logger.info(f'File "{uploaded_file.name}" uploaded successfully with file ID {uploaded_file.id}')
            return uploaded_file

        except Exception as e:
            logger.error(f"Error uploading file '{file_name}': {e}")
            return None
    
    def get_file_size(self, file_path):
        return os.path.getsize(file_path)
    
    def download_file(self, file_id, file_name=None, folder_path=None):
        """
        Downloads a file from Box by its file ID and saves it locally.

        Args:
            file_id (str): The ID of the file to download.

        Returns:
            str: The local path to the downloaded file.
        """
        if folder_path is not None:
            path = folder_path
        else:
            path = os.path.join(os.getcwd(), file_name)
        
        if file_name:
            file_name = file_name
        else:
            file_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        path = os.path.join(folder_path, file_name)


        try:
            # Download the file content
            with open(path, 'wb') as file:
                self.client.downloads.download_file_to_output_stream(file_id, file)
                logger.info(f"File '{file_name}' downloaded successfully with ID: {file_id}")

            return file_name
        except Exception as e:
            logger.error(f"Failed to download file '{file_id}': {e}")
            return None

    def download_files(self, folder_id, destination_folder_path=None):
        if destination_folder_path is None:
            destination_folder_path = self.unprocessed_videos_folder
        files = self.list_items_in_folder(folder_id)
        downloaded_files = []

        for file in files:
            downloaded_file = self.download_file(file['id'], file_name=file['name'], folder_path=destination_folder_path)
            downloaded_files.append(downloaded_file)
                    
        return downloaded_files
    
    def save_frames_to_long_term_storage(self, local_folder=None, destination_folder_id=None):
        logger.info(f"Placeholder for saving frames to long-term storage.")
        return 'success'

    def delete_file_by_id(self, file_id):
        """
        Deletes a file from Box by its file ID.

        Args:
            file_id (str): The ID of the file to delete.
        """
        try:
            self.client.files.delete_file_by_id(file_id)
            logger.info(f"File with ID '{file_id}' deleted successfully.")
        except Exception as e:
            logger.error(f"Failed to delete file '{file_id}': {e}")

    def get_user_by_email(self, user_email):
        """
        Retrieves a user by their email address.

        Args:
            user_email (str): The email address of the user to retrieve.

        Returns:
            dict: Information about the user.
        """
        try:
            user = self.client.users.get_users(filter_term=user_email)
            logger.info(f"User '{user_email}' found with ID: {user.id}")
            return user
        except Exception as e:
            logger.error(f"Failed to retrieve user '{user_email}': {e}")
            return None

    def share_folder_with_user_by_email(self, folder_id, user_email, role='viewer'):
        """
        Shares a folder with a user by their email address.

        Args:
            folder_id (str): The ID of the folder to share.
            user_email (str): The email address of the user to share with.
        """
        try:
            collaboration = self.client.user_collaborations.create_collaboration(
                item=CreateCollaborationItem(
                    type=CreateCollaborationItemTypeField.FOLDER,
                    id=folder_id
                ),
                accessible_by=CreateCollaborationAccessibleBy(
                    type=CreateCollaborationAccessibleByTypeField.USER,
                    login=user_email  # Use email directly instead of ID
                ),
                role=CreateCollaborationRole[role.upper()],  # Convert role string to enum
            )

            logger.info(f"Collaboration created: {user_email} → Folder {folder_id} as {role}")
            return collaboration

        except Exception as e:
            logger.error(f"Failed to create collaboration for {user_email}: {e}")
            return None


if __name__ == '__main__':

    # Initialize the Box client
    box_client = Box(BOX_CLIENT_ID, BOX_CLIENT_SECRET, BOX_ENTERPRISE_ID)

    unprocessed_videos_folder = unprocessed_videos_path

    box_items = box_client.list_items_in_folder('0')
    videos_folder_id = next(item for item in box_items if item['name'] == 'Videos')['id']
    box_client.videos_folder_box_id = videos_folder_id

    videos_folder_items = box_client.list_items_in_folder(videos_folder_id)
    print(f'{videos_folder_items = }')

    #box_client.share_folder_with_user_by_email(videos_folder_id, 'connor.mckinnis@carync.gov', role='editor')

    #box_client.upload_large_file_to_box(file_name='GX010014.mp4', file_path='unprocessed_videos/GX010014.MP4', parent_folder_id=box_client.videos_folder_box_id)

    