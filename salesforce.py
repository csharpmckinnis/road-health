import os
import json
from simple_salesforce import Salesforce
from PIL import Image
import base64
import dotenv
import logging
import io
import re


dotenv.load_dotenv()


class WorkOrderCreator:
    def __init__(
        self,
        username: str = None,
        password: str = None,
        security_token: str = None,
        client_id: str = None,
        metadata_folder: str = None,
        telemetry_items: list = None,
        sandbox: bool = False,
    ):
        """
        Initialize the WorkOrderCreator class with Salesforce authentication.

        :param metadata_folder: Path to the folder containing metadata JSON files.
        :param username: Salesforce username.
        :param password: Salesforce password.
        :param security_token: Salesforce security token.
        :param client_id: Custom client ID for logging purposes.
        :param sandbox: Boolean indicating whether to use a Salesforce sandbox.
        """

        self.all_metadata = telemetry_items if telemetry_items else []

        username = (
            username if username is not None else os.getenv("SALESFORCE_USERNAME_PROD")
        )
        password = (
            password if password is not None else os.getenv("SALESFORCE_PASSWORD_PROD")
        )
        security_token = (
            security_token
            if security_token is not None
            else os.getenv("SALESFORCE_SECURITY_TOKEN_PROD")
        )
        client_id = (
            client_id
            if client_id is not None
            else os.getenv("SALESFORCE_CONSUMER_KEY_PROD")
        )

        domain = (
            "test" if sandbox else "login"
        )  # Use 'test' for sandbox, 'login' for production
        self.sf_domain = "--sahara.sandbox" if domain == "test" else ""

        self.metadata_folder = (
            metadata_folder if metadata_folder is not None else "frames"
        )

        # Authenticate and initialize the Salesforce object
        self.sf = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
            client_id=client_id,
            domain=domain,
        )
        print(f"Authenticated successfully with Salesforce (sandbox={sandbox}).")

        self.coordinate_variance = 0.0002
        self.coordinate_variance_growth_factor = 0.001
        self.base_query = "SELECT Id, Name, Geolocation__latitude__s, Geolocation__longitude__s FROM Location__c"

    def create_ai_event(
        self,
        metadata_item=None,
        subject="Default",
        description="Default",
        box_file_url="https://upload.wikimedia.org/wikipedia/commons/c/c7/Pothole_Big.jpg",
    ):
        from geospatial import RoadOwnerFinder

        record_id = None
        lat_str = metadata_item.get("lat", 0)
        lon_str = metadata_item.get("lon", 0)
        lat = float(lat_str)
        lon = float(lon_str)
        road_owner_finder = RoadOwnerFinder(api_key=os.getenv("ARCGIS_API_KEY"))
        owner = road_owner_finder.get_pothole_owner(lat=lat, lon=lon)

        ai_event = {
            "Subject__c": subject,
            "Description__c": description,
            "Subject_Image_URL__c": box_file_url,
            "Location__Latitude__s": lat,
            "Location__Longitude__s": lon,
            "RecordTypeId": "012Ki0000004IAGIA2",
            "OwnerId": "00GKi000001OUQ2",
            "Location_Owner__c": owner,
        }

        response = self.sf.AI_Event__c.create(ai_event)
        record_id = response["id"]
        print(f"AI Event created successfully: {record_id}")

        return record_id

    def process_metadata_files(self):
        """
        Process metadata files and create Work Orders for high-confidence potholes.
        Stores all metadata in a self.all_metadata list for future use.
        """
        self.all_metadata = []  # Initialize or reset the list to store all metadata

        for file_name in os.listdir(self.metadata_folder):
            if not file_name.endswith(".json"):
                continue

            file_path = os.path.join(self.metadata_folder, file_name)
            try:
                with open(file_path, "r") as f:
                    metadata = json.load(f)
                    self.all_metadata.append(metadata)  # Add metadata to the list

            except Exception as e:
                print(f"Error processing file {file_name}: {e}")

        print(
            f"Processed {len(self.all_metadata)} metadata files. Stored in self.all_metadata."
        )

    async def ai_event_engine(self, box_client, telemetry_objects: list = None):
        try:
            ai_events_created = 0

            for object in telemetry_objects:
                analysis_results = object.analysis_results
                pothole = analysis_results.get("pothole", "no")
                pothole_confidence = analysis_results.get("pothole_confidence", 0)

                if pothole == "yes" and pothole_confidence > 0.9:
                    description = self.create_description_package(object.to_dict())
                    box_url = object.box_file_url
                    subject = (
                        f"Pothole Detected - Confidence {pothole_confidence * 100:.1f}%"
                    )

                    record_id = self.create_ai_event(
                        object.to_dict(), subject, description, box_url
                    )
                    ai_events_created += 1

                    print(f"Created AI Event with ID {record_id}")

        except Exception as e:
            logging.error(f"An error occurred in the AI Event Engine: {e}")
            return None

    def in_excluded_area(self, metadata_item):
        """Checks if the image is of a location in an excluded area.

        Args:
            metadata_item (_type_): _description_
        """
        in_excluded_area = False
        excluded_areas = [
            {
                "name": "James Jackson PW Facility",
                "lat_min": 35.796492,
                "lat_max": 35.800932,
                "lon_min": -78.798565,
                "lon_max": -78.810302,
            },
            {
                "name": "South Wake Landfill",
                "lat_min": 35.679923,
                "lat_max": 35.686232,
                "lon_min": -78.682376,
                "lon_max": -78.847694,
            },
        ]

        lat = float(metadata_item.get("lat", 0))
        lon = float(metadata_item.get("lon", 0))

        for area in excluded_areas:
            if (area["lat_min"] <= lat <= area["lat_max"]) and (
                area["lon_min"] <= lon <= area["lon_max"]
            ):
                in_excluded_area = True
                print(
                    f"DEBUG: Image at ({lat}, {lon}) is in excluded area: {area['name']}"
                )
                return in_excluded_area

        return in_excluded_area

    def get_nearby_street_segments(self, metadata_item):  # Subprocess
        print("DEBUG: Running get_nearby_street_segments")
        # starts a get_street_segments() run to get records from SF where:
        #   latitude is within +- coordinate variance
        #   longitude is within +- coordinate variance
        # If no segments returned, expand the coordinate variance and try again
        # Returns list of street segments and their coordinates when any are returned
        segments = []
        while not segments:
            results = self.get_street_segments(metadata_item)
            segments = results
            self.coordinate_variance += self.coordinate_variance_growth_factor

        simplified_locations = []
        for segment in segments:
            location = {
                "Id": segment.get("Id"),
                "Name": segment.get("Name"),
                "Latitude": segment.get("Geolocation__Latitude__s"),
                "Longitude": segment.get("Geolocation__Longitude__s"),
            }
            simplified_locations.append(location)

        return simplified_locations

    def get_street_segments(self, metadata_item):  # Subprocesses
        # Prep a query by adding the variance coordinates as +- conditions including WHERE
        # Run a query for street segments with the WHERE conditions added
        meta = metadata_item

        meta_lat_str = meta.get("lat", None)
        meta_lon_str = meta.get("lon", None)

        meta_lat = round(float(meta_lat_str), 4)
        meta_lon = round(float(meta_lon_str), 4)

        # Calculate lower and upper values for latitude and longitude searching
        lat_min = meta_lat - self.coordinate_variance
        lat_max = meta_lat + self.coordinate_variance
        lon_min = meta_lon - self.coordinate_variance
        lon_max = meta_lon + self.coordinate_variance
        conditions = f"WHERE (RecordTypeId = '0124u000000ciJTAAY' OR RecordTypeId = '0124u000000ciJSAAY') AND Geolocation__latitude__s >= {lat_min} AND Geolocation__latitude__s <= {lat_max} AND Geolocation__longitude__s >= {lon_min} AND Geolocation__longitude__s <= {lon_max}"

        results = self.sf.query(
            f"SELECT Id, Name, Geolocation__latitude__s, Geolocation__longitude__s FROM Location__c {conditions}"
        )
        results = results["records"]
        if len(results) == 0:
            results = None
        return results

    def expand_coordinate_variance(self):
        self.coordinate_variance += 0.0005

    def remove_timestamp(self, filename):
        return re.sub(r"^\d{8}_\d{2}_\d{2}_", "", filename)

    def get_closest_location(self, metadata_item):  # Main Process
        locations = self.get_nearby_street_segments(metadata_item)
        closest_location = None
        min_distance = float("inf")
        for loc in locations:
            distance = self.calculate_distance(metadata_item, loc)
            if distance < min_distance:
                min_distance = distance
                closest_location = loc

        return closest_location, min_distance

    def create_description_package(
        self, metadata_item, closest_sf_location=None, closest_sf_location_distance=None
    ):
        """
            Create a description package formatted as a rich text field for Salesforce.

            :param metadata_item: Metadata for the detected pothole (includes telemetry and AI analysis).
            :param closest_sf_location: Closest Salesforce location object (contains Id, Name, Latitude, Longitude).
            :param closest_sf_location_distance: Distance from the pothole to the closest Salesforce location in km.
            :return: A formatted string for the Salesforce rich text field.


            {
            "filename": "frame_0001.jpg",
            "filepath": "frames/frame_0001.jpg",
            "timestamp": "2024-09-26T16:33:34Z",
            "lat": 35.756189,
            "lon": -78.7451761,
            "openai_file_id": "file-5JXkUvVhDCJq6BiW3Mw6Ny",
            "analysis_results": {
                "file_id": "frame_0001.jpg",
                "pothole": "no",
                "pothole_confidence": 0.85,
                "alligator_cracking": "light",
                "line_cracking": "moderate",
                "raveling": "none",
                "summary": "The road exhibits significant alligator cracking and extensive line cracking, indicating structural distress. Overall condition is Poor.",
                "estimated_pcr": 42
            }
        }



        """
        # Extract metadata details
        ai_analysis = metadata_item.get("analysis_results", {})
        analysis_summary = ai_analysis.get("summary", "No analysis summary provided.")
        pothole = ai_analysis.get("pothole", None)
        pothole_confidence = ai_analysis.get("pothole_confidence", None)
        line_cracking = ai_analysis.get("line_cracking", "Unknown")
        alligator_cracking = ai_analysis.get("alligator_cracking", "Unknown")
        raveling = ai_analysis.get("raveling", "Unknown")
        est_pcr = ai_analysis.get("estimated_pcr", "nAn")
        lat = metadata_item.get("lat", "Unknown")
        lon = metadata_item.get("lon", "Unknown")

        # Construct assessment details
        assessment_details = []
        if pothole is not None:
            assessment_details.append(
                f"Pothole Presence: {'Yes' if pothole else 'No'} ({pothole_confidence * 100:.1f}%)"
            )
        if line_cracking is not None:
            assessment_details.append(f"Line Cracking: {line_cracking}")
        if alligator_cracking is not None:
            assessment_details.append(f"Alligator Cracking: {alligator_cracking}")
        if raveling is not None:
            assessment_details.append(f"Raveling: {raveling}")

        if est_pcr is not None:
            assessment_details.append(f"Estimated PCR: {est_pcr}")

        # Construct the Google Maps URL
        maps_url = f"https://www.google.com/maps/place/{lat},{lon}"

        # Construct the Static Resource URL
        # Format the description package
        description = (
            f"This Work Order was created by an automatic system due to a detected pothole."
            f"If this analysis is incorrect, or correction is not needed, please reject this record and do not act on it.\n\n"
            f"Analysis provided by the Road Health Analysis AI:\n"
            f"{analysis_summary}\n\n"
            f"Assessment Results:\n" + "\n".join(assessment_details) + "\n\n"
            f"To route to the best-estimated location of the detection, click this link:\n"
            f"{maps_url}\n"
        )

        return description

    def create_static_resource(self, image_file, quality=25):
        """
        Upload an image file as a Salesforce Static Resource and return its Id.

        :param image_file: File path to the image (jpg format).
        :return: Id of the created Static Resource.
        """
        try:
            # Check if file exists
            if not os.path.exists(image_file):
                raise FileNotFoundError(f"Image file '{image_file}' not found.")

            # Compress the image
            compressed_file = f"compressed_{os.path.basename(image_file)}"
            with Image.open(image_file) as img:
                img.save(compressed_file, "JPEG", quality=quality)

            # Read the image and encode it as base64
            with open(compressed_file, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")

            # Prepare the Static Resource name
            base_name = os.path.splitext(os.path.basename(image_file))[0]
            sanitized_name = "".join(
                c if c.isalnum() or c == "_" else "_" for c in base_name
            )
            resource_name = f"road_image_{sanitized_name}"

            # Construct the Static Resource payload
            static_resource = {
                "Name": resource_name,
                "ContentType": "image/jpeg",
                "Body": image_base64,
                "CacheControl": "Public",
            }

            # Create the Static Resource in Salesforce
            response = self.sf.StaticResource.create(static_resource)
            return response["id"], resource_name

        except Exception as e:
            print(f"An error occurred while creating the Static Resource: {e}")
            return None

    def upload_file_to_salesforce(self, file_path, record_id):
        """
        Upload a file as a Salesforce File and relate it to a record.

        :param file_path: The path to the file to upload.
        :param record_id: The Salesforce record Id to relate the file to.
        :return: The Id of the created ContentDocument.
        """
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File '{file_path}' not found.")

            # Compress the image in memory
            with Image.open(file_path) as img:
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format="JPEG", quality=25)
                img_byte_arr = img_byte_arr.getvalue()

            # Encode the image as base64
            file_data = base64.b64encode(img_byte_arr).decode("utf-8")

            # Get the file name from the path
            file_name = os.path.basename(file_path)

            # Create the ContentVersion record
            content_version = {
                "Title": file_name,
                "PathOnClient": file_name,
                "VersionData": file_data,
                "FirstPublishLocationId": record_id,
            }

            # Make the API call to create the ContentVersion
            response = self.sf.ContentVersion.create(content_version)

            # Retrieve the ContentDocumentId from the created ContentVersion
            content_version_id = response["id"]
            query = f"SELECT ContentDocumentId, Id FROM ContentVersion WHERE Id = '{content_version_id}'"
            result = self.sf.query(query)

            content_document_id = result["records"][0]["ContentDocumentId"]
            content_version_id = result["records"][0]["Id"]
            print(
                f"File uploaded successfully: ContentDocumentId = {content_document_id}"
            )

            return content_document_id, content_version_id

        except Exception as e:
            print(f"An error occurred while uploading the file: {e}")
            return None

    def calculate_distance(
        self, metadata_item, location
    ):  # Subprocess, returns est distance in km
        print("DEBUG: Running calculate_distance...")
        print(f"DEBUG: {location = }")
        meta = metadata_item

        meta_lat_str = meta.get("lat", None)
        meta_lon_str = meta.get("lon", None)

        meta_lat = round(float(meta_lat_str), 4)
        meta_lon = round(float(meta_lon_str), 4)

        loc_lat = location["Latitude"]
        loc_lon = location["Longitude"]

        print(f"DEBUG: {loc_lat = }")
        print(f"DEBUG: {loc_lon = }")

        lat_diff = loc_lat - meta_lat
        lon_diff = loc_lon - meta_lon
        return round(((lat_diff**2 + lon_diff**2) ** 0.5) * 110, 3)

    def post_image_to_chatter(
        self, work_order_id, image_content_document_id, message=None
    ):
        chatter_post_id = None
        # Need to create a Chatter post with the salesforce api, relate the post to the work order record, and attach the content document id as a FeedAttachment junction object
        try:
            response = self.sf.FeedItem.create(
                {
                    "ParentId": work_order_id,
                    "Body": message,
                    "RelatedRecordId": image_content_document_id,
                    "Type": "ContentPost",
                }
            )
            print(f"{response = }")
            chatter_post_id = response["id"]
            print(f"{chatter_post_id = }")
        except Exception as e:
            print(f"Failed to post image to Chatter: {e}")
        return chatter_post_id


if __name__ == "__main__":
    print("starting")

    """
    username = os.getenv("SALESFORCE_USERNAME")
    password = os.getenv("SALESFORCE_PASSWORD")
    security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
    client_id = os.getenv("SALESFORCE_CONSUMER_KEY")
    is_sandbox = True
    """
    username = os.getenv("SALESFORCE_USERNAME_PROD")
    password = os.getenv("SALESFORCE_PASSWORD_PROD")
    security_token = os.getenv("SALESFORCE_SECURITY_TOKEN_PROD")
    client_id = os.getenv("SALESFORCE_CONSUMER_KEY_PROD")
    is_sandbox = False

    print(
        f"{username = } \n{password = } \n{security_token = } \n{client_id = } \n{is_sandbox = }"
    )

    w_o_creator = WorkOrderCreator(
        username=username,
        password=password,
        security_token=security_token,
        client_id=client_id,
        sandbox=is_sandbox,
    )
    telem_obj = {
        "lat": 10.00000001,
        "lon": 88.00000002,
    }
    w_o_creator.create_ai_event(
        metadata_item=telem_obj, subject="TEST", description="TEST TEST"
    )
