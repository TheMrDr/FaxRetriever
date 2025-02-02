import re
from urllib.parse import quote_plus

from pymongo import MongoClient

# Define the MongoDB connection
username = quote_plus("Overflow6847")
password = quote_plus("tjZF2T%^q8aNh5^n*6^4!jjmPXD3%eDZbefzK64bhjhmY6RrBVH^5M6qH!QUQSNL")
host = "licensing.clinicnetworking.com"
port = 27017
database = "FaxRetriever"

uri = f"mongodb://{username}:{password}@{host}:{port}/?tlsAllowInvalidHostnames=true&tls=true&authSource={database}"
client = MongoClient(uri)
db = client[database]
accounts_collection = db["accounts"]


def check_org_identifier_status(org_identifier):
    """Checks if the org_identifier is active in the MongoDB."""
    account = accounts_collection.find_one(
        {"account_identifier": re.compile(f"^{re.escape(org_identifier)}$", re.IGNORECASE)})
    if account and account.get("active") is True:
        return True, "Active"
    return False, "Inactive or not found"


def extract_org_identifier(extension):
    """Extracts the organization identifier from the fax_user extension."""
    if '@' in extension:
        try:
            return extension.split('@')[1]
        except IndexError:
            return None
    else:
        return extension


def validate_fax_user(fax_user):
    """Validates the fax_user by querying MongoDB for the organization identifier."""
    org_identifier = extract_org_identifier(fax_user)

    if not org_identifier:
        print("Invalid extension format.")
        return False, "Invalid format"

    valid, status = check_org_identifier_status(org_identifier)
    return valid, status
