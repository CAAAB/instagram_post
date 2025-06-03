import json
import time
import random
import logging
import os
from datetime import datetime
import re
from dotenv import load_dotenv

# Third-party library imports
import requests  # Needs to be installed: pip install requests
from selenium import webdriver  # Needs to be installed: pip install selenium
# from instagrapi import Client  # Needs to be installed: pip install instagrapi

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

load_dotenv()

# --- User Configuration (loaded from .env file or defaults) ---
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
# IMGBB_API_KEY = os.getenv("IMGBB_API_KEY") # Removed as per instruction

CITY_CODES_STR = os.getenv("CITY_CODES", "")  # Default to empty string
CITY_CODES = [code.strip().upper() for code in CITY_CODES_STR.split(',') if code.strip()]
if not CITY_CODES:
    # Provide a default or example if not set in .env, useful for first run/dev
    CITY_CODES = ["PA"]
    print("Warning: CITY_CODES not found in .env, using default: ['PA']")


# Default settings (can be overridden by .env variables if desired later by adapting the code)
DAILY_POST_LIMIT = 20
MIN_POST_DELAY_MINUTES = 30
MAX_POST_DELAY_MINUTES = 120
# --- End User Configuration ---

# Basic logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

def get_data_urls_from_main_page():
    """
    Fetches the main page and extracts data URLs.

    Returns:
        dict: A dictionary containing the extracted URLs, or None if an error occurs.
    """
    main_page_url = "https://chborel.ch/mapinvaders/"
    urls = {}
    try:
        logging.info(f"Fetching data URLs from {main_page_url}")
        response = requests.get(main_page_url, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        content = response.text

        # Regex patterns to find the JavaScript variable assignments
        patterns = {
            "mapDataUrl": r"var\s+mapDataUrl\s*=\s*['\"]([^'\"]+)['\"]",
            "invaderSpotter": r"var\s+invaderSpotter\s*=\s*['\"]([^'\"]+)['\"]",
            "invaderSpotter2": r"var\s+invaderSpotter2\s*=\s*['\"]([^'\"]+)['\"]",
            "myMapUrl": r"var\s+myMapUrl\s*=\s*['\"]([^'\"]+)['\"]",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                urls[key] = match.group(1)
                logging.info(f"Found {key}: {urls[key]}")
            else:
                logging.warning(f"{key} not found in page content.")
                urls[key] = None # Explicitly set to None if not found

        if not all(urls.values()): # Check if any URL was not found
            logging.warning("One or more URLs were not found. Please check the page structure.")

        return urls

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching {main_page_url}: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while parsing URLs: {e}")
        return None

def fetch_json_data(data_urls: dict) -> dict:
    """
    Fetches JSON data from a list of URLs.

    Args:
        data_urls (dict): A dictionary of URLs to fetch JSON data from.
                          Expected keys: "mapDataUrl", "invaderSpotter", "invaderSpotter2", "myMapUrl".

    Returns:
        dict: A dictionary where keys are descriptive names and values are the parsed JSON objects.
              Returns an empty dict if errors occur for all URLs.
    """
    json_datasets = {}
    # Descriptive keys mapping to the keys in data_urls
    url_key_map = {
        "map_data": "mapDataUrl",
        "spotter_data_1": "invaderSpotter",
        "spotter_data_2": "invaderSpotter2",
        "my_map_data": "myMapUrl",
    }

    for descriptive_key, url_dict_key in url_key_map.items():
        url = data_urls.get(url_dict_key)
        if not url:
            logging.warning(f"URL for '{descriptive_key}' ({url_dict_key}) not found in data_urls. Skipping.")
            json_datasets[descriptive_key] = None
            continue

        try:
            logging.info(f"Fetching JSON data from {url} for '{descriptive_key}'")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            json_datasets[descriptive_key] = response.json()
            logging.info(f"Successfully fetched and parsed JSON for '{descriptive_key}'.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching {url} for '{descriptive_key}': {e}")
            json_datasets[descriptive_key] = None
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON from {url} for '{descriptive_key}': {e}")
            json_datasets[descriptive_key] = None
        except Exception as e:
            logging.error(f"An unexpected error occurred while fetching/parsing JSON for '{descriptive_key}' from {url}: {e}")
            json_datasets[descriptive_key] = None

    return json_datasets

# Helper functions
def python_deep_merge(target: dict, source: dict) -> dict:
    """
    Deeply merges source dict into target dict.
    Modifies target in place and also returns it.
    """
    for key, value in source.items():
        if isinstance(value, dict):
            # get node or create one
            node = target.setdefault(key, {})
            python_deep_merge(node, value)
        else:
            target[key] = value
    return target

def python_get_value(obj: dict, path: str, default=None):
    """
    Gets a value from a nested dict using a dot-separated path.
    e.g., python_get_value(data, "user.profile.name")
    """
    keys = path.split('.')
    for key in keys:
        if isinstance(obj, dict) and key in obj:
            obj = obj[key]
        elif isinstance(obj, list) and key.isdigit() and int(key) < len(obj):
            obj = obj[int(key)]
        else:
            return default
    return obj

def _normalize_city_name(city_name: str) -> str:
    """Normalizes city names like 'Paris - X' to 'Paris'."""
    if city_name is None:
        return ""
    return city_name.split(' - ')[0].strip()

def consolidate_data_python(json_datasets: dict) -> dict:
    """
    Consolidates invader data from multiple JSON sources into a single dictionary.
    """
    invaders_consolidated_python = {}

    # 1. Initial Data Preparation
    map_data_list = list(json_datasets.get("map_data", [])) # Work with a copy
    spotter_data_1 = json_datasets.get("spotter_data_1", {}).get("invaders", {})
    spotter_data_2 = json_datasets.get("spotter_data_2", {}).get("invaders", {})
    my_map_data_list = json_datasets.get("my_map_data", [])

    # Mimic renameStatusField for spotter_data_2 (if needed, assuming 'status' is the target field)
    # In JS, it was: data.invaders[invaderId].status_history.forEach(h => h.status_IS = h.status);
    # This implies that status_IS should be a copy of status IF 'status' exists.
    # For simplicity, we'll assume the fields are already named consistently or handle during access.
    # The JS code also deleted the old 'status' field.
    for invader_id, invader_details in spotter_data_2.items():
        if 'status_history' in invader_details and isinstance(invader_details['status_history'], list):
            for history_entry in invader_details['status_history']:
                if 'status' in history_entry:
                    history_entry['status_IS'] = history_entry['status']
                    # del history_entry['status'] # Optional: if strict schema is required

    merged_invader_spotter_data = python_deep_merge(dict(spotter_data_1), spotter_data_2)

    # Add SPACE_02 record to map_data
    space_02_exists = any(invader.get("id") == "SPACE_02" for invader in map_data_list)
    if not space_02_exists:
        map_data_list.append({
            "id": "SPACE_02", "status": "ALIVE", "hint": "In orbit",
            "instagramUrl": "", "obf_lat": 0, "obf_lng": 0
        })

    additional_map_data = {
        item["id"]: {"my_lat": item["obf_lat"], "my_lng": item["obf_lng"]}
        for item in my_map_data_list if "id" in item and "obf_lat" in item and "obf_lng" in item
    }

    merged_map_data_dict = {item["id"]: item for item in map_data_list}
    for invader_id, extra_data in additional_map_data.items():
        if invader_id in merged_map_data_dict:
            merged_map_data_dict[invader_id].update(extra_data)
        else:
            # If my_map_data has an invader not in map_data_list, create a new entry
            merged_map_data_dict[invader_id] = {
                "id": invader_id,
                "status": "UNKNOWN", # Default status
                "hint": "",
                "instagramUrl": "",
                "obf_lat": None, # No base lat/lng if not in map_data_list
                "obf_lng": None,
                **extra_data
            }

    # 2. Core Consolidation Logic
    def get_all_invader_ids(map_d_dict, flashes_data, invaders_spotter_data, manual_d):
        # flashes_data and manual_d are not used yet by the bot, pass as {} or None
        ids = set()
        for k in map_d_dict.keys(): ids.add(k)
        for k in invaders_spotter_data.keys(): ids.add(k)
        # if flashes_data:
        #     for k in flashes_data.keys(): ids.add(k)
        # if manual_d:
        #     for k in manual_d.keys(): ids.add(k)
        return list(ids)

    all_invader_ids = get_all_invader_ids(merged_map_data_dict, {}, merged_invader_spotter_data, {})
    logging.info(f"Found {len(all_invader_ids)} unique invader IDs to process.")

    for invader_id in all_invader_ids:
        invader_spotter_entry = merged_invader_spotter_data.get(invader_id, {})
        map_entry = merged_map_data_dict.get(invader_id, {})

        # Status history and related fields from invader_spotter_data
        status_history_raw = python_get_value(invader_spotter_entry, "status_history", [])
        status_history_sorted = sorted(status_history_raw, key=lambda x: x.get("updateDate", 0), reverse=True)

        status_last = python_get_value(status_history_sorted, "0.status_IS", "UNKNOWN") # status_IS after potential rename
        latest_update_date = python_get_value(status_history_sorted, "0.updateDate")
        first_update_date = python_get_value(status_history_sorted, f"{len(status_history_sorted)-1}.updateDate") if status_history_sorted else None

        status_reactivated = False
        if len(status_history_sorted) > 1:
            for i in range(len(status_history_sorted) -1):
                if status_history_sorted[i].get("status_IS") == "A" and status_history_sorted[i+1].get("status_IS") != "A":
                    status_reactivated = True
                    break

        city_name_from_spotter = python_get_value(invader_spotter_entry, "city")
        city_name_from_map = python_get_value(map_entry, "city") # Assuming map_entry might have city

        city_raw = city_name_from_spotter or city_name_from_map or invader_id.split('_')[0]
        city = _normalize_city_name(city_raw)

        # Default values for the consolidated entry
        entry = {
            "name": invader_id,
            "status_manual": "", # Not yet handled by bot
            "status_invaders": status_last, # From invader_spotter
            "status_invaders_update": latest_update_date,
            "status_reactivated": status_reactivated,
            "status_last": status_last, # Will be updated by dynamic property logic later if needed
            "status_invaders_history": status_history_sorted,
            "status_invaders2": python_get_value(invader_spotter_entry, "status_IS_v2", "UNKNOWN"), # Assuming a v2 status if available
            "status_mapD": python_get_value(map_entry, "status", "UNKNOWN"),
            "city_id": "", # Not available directly
            "city": city,
            "obf_lat": python_get_value(map_entry, "obf_lat"),
            "obf_lng": python_get_value(map_entry, "obf_lng"),
            "my_lat": python_get_value(map_entry, "my_lat"), # From additional_map_data merged into map_entry
            "my_lng": python_get_value(map_entry, "my_lng"),
            "user_lat": None, # Not yet handled
            "user_lng": None, # Not yet handled
            "image_url_flashes": "", # Not yet handled
            "image_url_invaders": python_get_value(invader_spotter_entry, "url"),
            "point_flashes": "", # Not yet handled
            "point_invaders": python_get_value(invader_spotter_entry, "points"),
            "date_pos_flashes": "", # Not yet handled
            "date_pos_invaders": first_update_date, # Or latest_update_date, JS used firstUpdateDate here
            "date_flash_auto": None, # Not yet handled (related to flashes data)
            "date_flash_manual": None, # Not yet handled
            "is_flashed_auto": False, # Not yet handled
            "is_flashed_manual": False, # Not yet handled
            "is_destroyed_auto": status_last in ["D", "X", "W"], # Based on invader_spotter status
            "is_destroyed_manual": False, # Not yet handled
            "instagramUrl": python_get_value(map_entry, "instagramUrl"),
            "hint": python_get_value(map_entry, "hint"),
            "comment": "", # Not yet handled
            "oldComment": "", # Not yet handled
            "order": 0 # Will be assigned after sorting
        }

        # Dynamic properties as functions (or methods if using a class)
        # These will be called with the entry itself if they need internal values not directly available here
        # For simplicity, some logic is directly computed or uses defaults for now.

        # `image_url`: chooses between `image_url_flashes` or `image_url_invaders`.
        entry["final_image_url"] = entry["image_url_flashes"] or entry["image_url_invaders"]

        # `point`: chooses between `point_flashes` or `point_invaders`.
        entry["final_point"] = entry["point_flashes"] or entry["point_invaders"]

        # `date_pos`: chooses between `date_pos_flashes`, `date_pos_invaders`, or `firstUpdateDate`.
        entry["final_date_pos"] = entry["date_pos_flashes"] or entry["date_pos_invaders"] or first_update_date

        # `date_flash`: chooses between `date_flash_auto` or `date_flash_manual`.
        entry["final_date_flash"] = entry["date_flash_auto"] or entry["date_flash_manual"]

        # `is_manual`: checks if `comment` is present, or `is_flashed_manual`, or `is_destroyed_manual`, or `user_lat` is present.
        entry["final_is_manual"] = bool(entry["comment"] or entry["is_flashed_manual"] or entry["is_destroyed_manual"] or entry["user_lat"])

        # `is_flashed`: checks `is_flashed_auto` or `is_flashed_manual`.
        entry["final_is_flashed"] = entry["is_flashed_auto"] or entry["is_flashed_manual"]

        # `is_destroyed`: checks `is_destroyed_manual` or `is_destroyed_auto`.
        entry["final_is_destroyed"] = entry["is_destroyed_manual"] or entry["is_destroyed_auto"]

        # `getLatLng`: prioritizes coordinates: user_lat/lng, then my_lat/lng, then obf_lat/lng.
        lat, lng = None, None
        if entry["user_lat"] is not None and entry["user_lng"] is not None:
            lat, lng = entry["user_lat"], entry["user_lng"]
        elif entry["my_lat"] is not None and entry["my_lng"] is not None:
            lat, lng = entry["my_lat"], entry["my_lng"]
        elif entry["obf_lat"] is not None and entry["obf_lng"] is not None:
            lat, lng = entry["obf_lat"], entry["obf_lng"]
        entry["final_lat"] = lat
        entry["final_lng"] = lng

        # Update status_last based on manual data if available (not yet implemented)
        # if entry["status_manual"]: entry["status_last"] = entry["status_manual"]
        # elif entry["is_destroyed_manual"]: entry["status_last"] = "D"
        # elif entry["is_flashed_manual"]: entry["status_last"] = "A"
        # else: entry["status_last"] = entry["status_invaders"] or entry["status_mapD"]
        if entry["status_manual"]:
             entry["status_last"] = entry["status_manual"]
        # Placeholder for manual destroyed/flashed status update:
        # elif entry["is_destroyed_manual"]: entry["status_last"] = "D"
        # elif entry["is_flashed_manual"]: entry["status_last"] = "A"
        elif not entry["status_invaders"] or entry["status_invaders"] == "UNKNOWN":
            # If status_invaders is empty or UNKNOWN, fallback to status_mapD
            map_status = entry["status_mapD"]
            if map_status: # Ensure map_status is not None or empty
                if map_status.lower() in ["destroyed", "dead", "x"]: # example normalizations
                    entry["status_last"] = "D"
                elif map_status.lower() in ["ok", "alive", "active", "a"]:
                    entry["status_last"] = "A"
                elif map_status.lower() in ["wounded", "w"]:
                    entry["status_last"] = "W"
                # Add other normalizations if necessary
                else:
                    entry["status_last"] = map_status.upper() # Convert to upper if no direct mapping, or keep as UNKNOWN
            else:
                entry["status_last"] = "UNKNOWN" # If map_status is also empty
        # else, status_last remains as status_invaders (already set, assumed to be uppercase or UNKNOWN)

        # Re-evaluate is_destroyed_auto based on the potentially updated status_last
        entry["is_destroyed_auto"] = entry["status_last"] in ["D", "X", "W"] # Expects uppercase
        entry["final_is_destroyed"] = entry["is_destroyed_manual"] or entry["is_destroyed_auto"]


        invaders_consolidated_python[invader_id] = entry

    # Sort by date_flash to assign order (mimicking JS)
    # Since date_flash is not fully implemented (depends on user flashes), this sort might not be meaningful yet.
    # Using 'final_date_pos' or 'status_invaders_update' as a proxy for now if 'final_date_flash' is None

    # Filter out entries where the sort key might be None to avoid runtime errors
    # Choose a fallback date like 0 (epoch start) if primary date keys are None
    # The JS code sorts by `date_flash` which is `date_flash_auto` or `date_flash_manual`.
    # If these are not set, it might default to null/undefined, affecting sort order.
    # We'll use `status_invaders_update` (latestUpdateDate) as a primary sort key if final_date_flash is None.

    sorted_invaders = sorted(
        invaders_consolidated_python.values(),
        key=lambda x: x.get("final_date_flash") or x.get("status_invaders_update") or 0, # Ensure non-None for sorting
        reverse=True # Assuming more recent is "smaller" order or JS sorts ascending and then reverses
    )

    for i, invader_data in enumerate(sorted_invaders):
        invaders_consolidated_python[invader_data["name"]]["order"] = i + 1 # 1-based order

    return invaders_consolidated_python

def take_city_screenshot(city_code: str, output_path: str) -> bool:
    """
    Takes a screenshot of the specified city's map page.

    Args:
        city_code (str): The city code (e.g., "PA" for Paris).
        output_path (str): The path to save the screenshot.

    Returns:
        bool: True if screenshot was taken successfully, False otherwise.
    """
    logging.info(f"Attempting to take screenshot for city code: {city_code.upper()} to {output_path}")

    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu") # Often necessary for headless
    chrome_options.add_argument("--window-size=1920,1200") # Larger height for potentially tall city maps
    chrome_options.add_argument("--no-sandbox") # Bypass OS security model, REQUIRED for Docker/CI
    chrome_options.add_argument("--disable-dev-shm-usage") # overcome limited resource problems
    chrome_options.add_argument("--log-level=3") # Suppress INFO/WARNING console logs from Chrome
    chrome_options.add_argument("--disable-extensions") # Ensure a clean browsing environment
    chrome_options.add_argument("--disable-popup-blocking") # Try to prevent popups from interfering

    driver = None
    try:
        logging.info("Initializing Chrome WebDriver...")
        # Use try-except for WebDriver initialization as it can fail
        try:
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        except Exception as e:
            logging.error(f"Failed to initialize WebDriver: {e}")
            # Attempt to find chromedriver in PATH if install fails (common in restricted envs)
            logging.info("Attempting to use chromedriver from PATH if available...")
            try:
                driver = webdriver.Chrome(options=chrome_options)
            except Exception as e_path:
                logging.error(f"Failed to initialize WebDriver from PATH as well: {e_path}")
                return False

        logging.info("WebDriver initialized.")

        url = f"https://chborel.ch/mapinvaders/?city={city_code.upper()}"
        logging.info(f"Navigating to {url}")
        driver.get(url)

        logging.info("Waiting for map element (ID: 'map') to be present...")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.ID, "map"))) # Increased timeout
        logging.info("Map element is present.")

        # Additional wait for map tiles and invader markers to load and render
        # The navigateToCity function might take some time to pan/zoom and display markers.
        # Also, there might be an initial animation or loading screen.
        # Checking for invader markers is complex as they are dynamically added.
        # A longer sleep is a pragmatic approach here.
        # Let's also check for the loading overlay to disappear.
        try:
            loading_overlay_xpath = "//div[contains(@class, 'loading-overlay') and contains(@style, 'display: none')]"
            logging.info("Waiting for loading overlay to disappear (if present)...")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, loading_overlay_xpath))
            )
            logging.info("Loading overlay is gone or was not present.")
        except Exception: # TimeoutException if overlay doesn't disappear or isn't there
            logging.info("Loading overlay did not disappear in time or was not found, proceeding anyway.")

        # Wait for markers to potentially appear. Markers are img elements with class 'leaflet-marker-icon'.
        # We can wait for at least one such marker.
        try:
            logging.info("Waiting for at least one invader marker to appear...")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "img.leaflet-marker-icon"))
            )
            logging.info("At least one invader marker found.")
        except Exception: # TimeoutException
            logging.warning("No invader markers detected within the timeout. The city might have no invaders or map is not loading as expected.")


        # Final fixed delay for any JavaScript execution to settle after markers appear
        render_wait_time = 15 # Increased from 10
        logging.info(f"Waiting an additional {render_wait_time} seconds for rendering to settle...")
        time.sleep(render_wait_time)

        logging.info("Taking screenshot...")
        driver.save_screenshot(output_path)
        logging.info(f"Screenshot saved to {output_path}")
        return True

    except requests.exceptions.RequestException as e: # Catch potential errors if webdriver_manager fails to download
        logging.error(f"RequestException during WebDriver setup (e.g., downloading chromedriver): {e}")
        return False
    except Exception as e:
        logging.error(f"An error occurred during screenshot generation for {city_code}: {e}", exc_info=True)
        return False
    finally:
        if driver:
            logging.info("Quitting WebDriver.")
            driver.quit()

def upload_to_imgbb(image_path: str, api_key: str, expiration_seconds: int = 3600) -> str | None:
    """
    Uploads an image to ImgBB.

    Args:
        image_path (str): Path to the local image file.
        api_key (str): ImgBB API key.
        expiration_seconds (int): Optional. Expiration time for the image in seconds. Defaults to 3600 (1 hour).

    Returns:
        str | None: The direct URL of the uploaded image if successful, otherwise None.
    """
    if not api_key:
        logging.error("ImgBB API key is missing. Cannot upload image.")
        return None

    logging.info(f"Attempting to upload image {image_path} to ImgBB.")
    url = "https://api.imgbb.com/1/upload"

    try:
        with open(image_path, "rb") as image_file:
            payload = {
                "key": api_key,
                "expiration": expiration_seconds,
            }
            files = {
                "image": image_file
            }
            response = requests.post(url, data=payload, files=files, timeout=30)
            response.raise_for_status()  # Raise an exception for bad status codes

            response_json = response.json()

            if response_json.get("success") is True and response_json.get("data") and response_json["data"].get("url"):
                image_url = response_json["data"]["url"]
                logging.info(f"Image successfully uploaded to ImgBB: {image_url}")
                return image_url
            else:
                error_message = response_json.get("error", {}).get("message", "Unknown error")
                status_code = response_json.get("status_code", "N/A")
                logging.error(f"ImgBB upload failed. Status: {status_code}, Error: {error_message}, Full response: {response_json}")
                return None

    except FileNotFoundError:
        logging.error(f"Image file not found at {image_path}.")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error during ImgBB upload request: {e}")
        return None
    except json.JSONDecodeError:
        logging.error(f"Failed to decode JSON response from ImgBB: {response.text}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during ImgBB upload: {e}", exc_info=True)
        return None

def post_to_instagram(image_url: str, caption: str, username: str, password: str) -> str | None:
    """
    Posts an image to Instagram using the instagrapi library.

    Args:
        image_url (str): The public URL of the image to post.
        caption (str): The caption for the Instagram post.
        username (str): Instagram username.
        password (str): Instagram password.

    Returns:
        str | None: The media ID (pk) of the post if successful, otherwise None.
    """
    if not username or not password:
        logging.error("Instagram username or password not provided. Cannot post.")
        return None

    logging.info(f"Attempting to post image {image_url} to Instagram account {username}.")

    # Ensure instagrapi is imported (was commented out at the top level)
    try:
        from instagrapi import Client
        from instagrapi.exceptions import LoginRequired, TwoFactorRequired, BadPassword
    except ImportError:
        logging.error("instagrapi library is not installed. Please install it: pip install instagrapi")
        return None

    client = Client()
    # client.set_proxy("http://your_proxy_if_needed") # Example proxy
    # client.load_settings('session.json') # Example for loading session

    try:
        logging.info("Logging into Instagram...")
        # For testing with dummy credentials, this login will likely fail.
        # In a real scenario, proper error handling for 2FA, checkpoints, etc., is crucial.
        client.login(username, password)
        logging.info("Successfully logged into Instagram.")

        # client.dump_settings('session.json') # Example for saving session

        logging.info(f"Uploading photo from URL: {image_url} with caption: '{caption[:30]}...'")
        # instagrapi can handle image URLs directly in photo_upload
        media = client.photo_upload(path=image_url, caption=caption)

        if media and hasattr(media, 'pk'):
            logging.info(f"Successfully posted to Instagram. Media PK: {media.pk}")
            return str(media.pk)
        else:
            logging.error("Instagram post failed. Media object was not returned or has no PK.")
            return None

    except (LoginRequired, BadPassword) as e:
        logging.error(f"Instagram login failed: {e}. Please check credentials or session. 2FA might be an issue if not handled.")
        return None
    except TwoFactorRequired as e:
        logging.error(f"Instagram login failed due to 2FA being required: {e}. The bot needs to be adapted for 2FA.")
        # Example:
        # code = input("Enter 2FA code: ")
        # client.two_factor_login(code)
        return None
    except Exception as e:
        logging.error(f"An error occurred during Instagram posting: {e}", exc_info=True)
        return None
    # finally:
        # client.logout() # instagrapi typically manages sessions; explicit logout might not be needed unless issues arise.

def main():
    """Main function to run the Instagram bot."""
    logging.info("Instagram bot started. Initializing...")

    # --- Configuration Access and Checks ---
    # Variables are now loaded globally from .env or defaults defined above.

    # Create screenshots directory
    os.makedirs("screenshots", exist_ok=True)
    logging.info("Ensured 'screenshots' directory exists.")

    if not CITY_CODES: # This check is now against the potentially .env loaded list
        logging.error("CITY_CODES list is empty (after trying to load from .env). Please populate it. Exiting.")
        return

    # Credential checks
    # if not IMGBB_API_KEY: # Removed
    #     logging.warning("IMGBB_API_KEY is not set in .env. Image uploads will fail.")
    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        logging.warning("INSTAGRAM_USERNAME or INSTAGRAM_PASSWORD are not set in .env. Instagram posts will fail.")

    posted_invaders_log_file = "posted_invaders.csv"
    if not os.path.exists(posted_invaders_log_file):
        try:
            with open(posted_invaders_log_file, "w", encoding="utf-8") as f:
                f.write("city_code,invader_id,media_id,timestamp_utc\n")
            logging.info(f"Created posted invaders log file: {posted_invaders_log_file}")
        except IOError as e:
            logging.error(f"Failed to create posted invaders log file: {e}. Exiting.")
            return

    daily_post_count = 0
    # Optional: Load existing log to check daily_post_count or recently posted invaders
    # For now, we start fresh daily_post_count = 0 each run.

    # --- Data Extraction ---
    logging.info("Fetching and consolidating invader data...")
    data_urls = get_data_urls_from_main_page()
    if not data_urls:
        logging.error("Failed to get data URLs. Exiting.")
        return

    json_datasets = fetch_json_data(data_urls)
    if not any(json_datasets.values()): # Check if all datasets are None or empty
        logging.error("Failed to fetch JSON datasets or all datasets are empty. Exiting.")
        return

    invaders_data = consolidate_data_python(json_datasets)
    if not invaders_data:
        logging.error("Failed to consolidate invader data or no data found. Exiting.")
        return
    logging.info(f"Successfully processed data for {len(invaders_data)} total invaders.")

    # --- Main Loop through Cities ---
    # screenshot_path = "temp_city_screenshot.png" # Old path

    for city_code_idx, city_code in enumerate(CITY_CODES):
        screenshot_path = os.path.join("screenshots", f"{city_code.lower()}_map_screenshot.png") # New path per city

        if daily_post_count >= DAILY_POST_LIMIT:
            logging.info(f"Daily post limit of {DAILY_POST_LIMIT} reached. Stopping further posts for today.")
            break

        logging.info(f"Processing city: {city_code.upper()} ({city_code_idx + 1}/{len(CITY_CODES)})")

        city_invader_ids = [
            inv_id for inv_id in invaders_data
            if inv_id.upper().startswith(city_code.upper() + "_")
        ]

        if not city_invader_ids:
            logging.info(f"No invaders found for city code {city_code.upper()}. Skipping.")
            continue

        logging.info(f"Found {len(city_invader_ids)} invaders for {city_code.upper()}.")

        # Take Screenshot for the current city
        logging.info(f"Taking screenshot for {city_code.upper()}...")
        screenshot_success = take_city_screenshot(city_code, screenshot_path)
        if not screenshot_success:
            logging.error(f"Failed to take screenshot for {city_code.upper()}. Skipping this city.")
            continue

        # Prepare Hashtags and Captions
        city_invader_hashtags = [f"#{inv_id.replace('_', '')}" for inv_id in city_invader_ids] # e.g. #PA01
        max_hashtags_per_post = 20 # As per Instagram limits (max 30, using 20 to be safe with other tags)

        # Calculate how many posts are needed for this city's invaders
        num_posts_for_city = (len(city_invader_hashtags) + max_hashtags_per_post - 1) // max_hashtags_per_post
        logging.info(f"City {city_code.upper()} will require {num_posts_for_city} post(s).")

        # Loop for Each Post Segment in the City
        for i in range(num_posts_for_city):
            if daily_post_count >= DAILY_POST_LIMIT:
                logging.info(f"Daily post limit reached during segments for {city_code.upper()}.")
                break # Break from segment loop

            start_index = i * max_hashtags_per_post
            end_index = start_index + max_hashtags_per_post

            current_hashtags_segment = city_invader_hashtags[start_index:end_index]
            current_invaders_segment_ids = city_invader_ids[start_index:end_index]

            # Create caption
            caption_text = (f"Space Invaders in {city_code.upper()}! "
                            f"Segment {i+1}/{num_posts_for_city}.\n"
                            f"{' '.join(current_hashtags_segment)}\n\n"
                            f"#SpaceInvaders #Invader #MapInvaders #{city_code.upper()}Invaders #StreetArt{city_code.upper()}")

            logging.info(f"Preparing post {i+1}/{num_posts_for_city} for {city_code.upper()} with {len(current_hashtags_segment)} invader hashtags.")

            # Upload to ImgBB
            if not IMGBB_API_KEY: # Added explicit check here before attempting upload
                logging.error("IMGBB_API_KEY is not configured. Cannot upload image. Skipping post for this segment.")
                # If ImgBB key is missing, we probably want to stop trying for this city.
                break # Break from segment loop for this city

            image_url = upload_to_imgbb(screenshot_path, IMGBB_API_KEY)
            if image_url is None:
                logging.error(f"ImgBB upload failed for {city_code.upper()} segment {i+1}. Skipping further posts for this city.")
                break # Break from segment loop for this city

            # Post to Instagram
            if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD: # Explicit check
                logging.error("Instagram credentials are not configured. Cannot post. Skipping post for this segment.")
                # If credentials missing, probably stop trying for this city's segments too.
                # Or potentially allow it to fail inside post_to_instagram if we want to test its internal handling
                continue # Continue to next segment, but it will also fail this check or inside post_to_instagram

            media_id = post_to_instagram(image_url, caption_text, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

            if media_id:
                logging.info(f"Successfully posted segment {i+1} for {city_code.upper()}. Media ID: {media_id}")
                daily_post_count += 1

                # Log posted invaders for this segment
                try:
                    with open(posted_invaders_log_file, "a", encoding="utf-8") as f_log:
                        for invader_id in current_invaders_segment_ids:
                            f_log.write(f"{city_code},{invader_id},{media_id},{datetime.utcnow().isoformat()}\n")
                    logging.info(f"Logged {len(current_invaders_segment_ids)} invaders for media ID {media_id}.")
                except IOError as e:
                    logging.error(f"Failed to write to posted invaders log: {e}")

                # Randomized Delay if not the very last post of the entire run
                is_last_segment_for_city = (i == num_posts_for_city - 1)
                is_last_city = (city_code_idx == len(CITY_CODES) - 1)

                if not (is_last_segment_for_city and is_last_city) and daily_post_count < DAILY_POST_LIMIT :
                    delay_seconds = random.randint(MIN_POST_DELAY_MINUTES * 60, MAX_POST_DELAY_MINUTES * 60)
                    logging.info(f"Delaying next post by {delay_seconds // 60} minutes ({delay_seconds} seconds).")
                    time.sleep(delay_seconds)
            else:
                logging.error(f"Failed to post segment {i+1} for {city_code.upper()} to Instagram.")
                # Decide if we should break or continue. If post_to_instagram fails (e.g. login issue),
                # subsequent attempts in this run are also likely to fail.
                # For now, let's break from segments of this city if a post fails.
                logging.warning(f"Stopping further segments for city {city_code.upper()} due to Instagram post failure.")
                break # Break from segment loop

    # Cleanup Screenshot after all processing for a city (or all cities if screenshot_path is global)
    # Moved cleanup to after all loops if screenshot_path is global for all cities.
    # If screenshot is per city and path changes, then it should be inside city loop.
    # For now, I will *not* automatically delete them from screenshots/ as they might be useful.
    # The .gitignore will prevent them from being committed.

    logging.info("Instagram bot run completed.")

# Remove old single screenshot function
# def take_city_screenshot(city_code: str, output_path: str) -> bool: ...

def take_screenshots_for_cities(city_codes: list, invaders_data: dict, base_output_dir: str) -> dict:
    """
    Takes screenshots for a list of cities by navigating on a single map page.
    One browser instance is opened, and JavaScript is used to navigate between cities.

    Args:
        city_codes (list): A list of city codes (e.g., ["PA", "LDN"]).
        invaders_data (dict): Consolidated invader data to count invaders per city for filenames.
        base_output_dir (str): The base directory to save screenshots (e.g., "screenshots").

    Returns:
        dict: A dictionary mapping city_code to its screenshot path. Empty if errors occur.
    """
    logging.info(f"Starting screenshot process for {len(city_codes)} cities.")
    screenshot_paths = {}

    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1200") # Adjusted for potentially taller maps
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-popup-blocking")

    driver = None
    try:
        logging.info("Initializing Chrome WebDriver for multi-city screenshots...")
        try:
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        except Exception as e:
            logging.error(f"Failed to initialize WebDriver with manager: {e}")
            logging.info("Attempting to use chromedriver from PATH...")
            try:
                driver = webdriver.Chrome(options=chrome_options)
            except Exception as e_path:
                logging.error(f"Failed to initialize WebDriver from PATH: {e_path}")
                return screenshot_paths # Return empty if driver fails

        logging.info("WebDriver initialized. Navigating to base map page...")
        driver.get("https://chborel.ch/mapinvaders/")

        logging.info("Waiting for main map element (ID: 'map') to be present...")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.ID, "map")))
        logging.info("Main map element is present. Initial page load settling for 5 seconds...")
        time.sleep(5) # Allow initial map JavaScript to load and settle

        for city_code in city_codes:
            logging.info(f"Processing screenshot for city: {city_code.upper()}")

            js_command = f"navigateToCity('{city_code.upper()}');"
            logging.info(f"Executing JS: {js_command}")
            driver.execute_script(js_command)

            # Wait for navigation and map rendering for the specific city
            # This is a critical part; a fixed delay is a starting point.
            # More advanced checks could involve looking for city-specific markers if their structure is known
            # or waiting for some element that changes upon city navigation.
            city_render_delay = 15 # Increased delay after JS navigation
            logging.info(f"Waiting {city_render_delay} seconds for {city_code.upper()} map to render after navigateToCity...")
            time.sleep(city_render_delay)

            # Optional: Try to wait for markers again, specific to Leaflet if possible
            try:
                logging.info(f"Waiting for at least one invader marker for {city_code.upper()}...")
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "img.leaflet-marker-icon"))
                )
                logging.info(f"At least one invader marker found for {city_code.upper()}.")
                time.sleep(5) # Extra short delay if markers found
            except Exception: # TimeoutException
                logging.warning(f"No invader markers detected for {city_code.upper()} within timeout. Screenshot might be empty or map not fully loaded.")

            # Determine invader count for filename
            invader_count = sum(1 for inv_id in invaders_data if inv_id.upper().startswith(city_code.upper() + "_"))

            output_filename = f"{city_code.lower()}_invaders_{invader_count}.png"
            output_path = os.path.join(base_output_dir, output_filename)

            logging.info(f"Taking screenshot for {city_code.upper()} ({invader_count} invaders) -> {output_path}")
            driver.save_screenshot(output_path)
            screenshot_paths[city_code] = output_path
            logging.info(f"Screenshot for {city_code.upper()} saved.")

            # Small random delay between city navigations
            inter_city_delay = random.uniform(2, 5)
            logging.info(f"Waiting {inter_city_delay:.2f} seconds before next city...")
            time.sleep(inter_city_delay)

    except requests.exceptions.RequestException as e:
        logging.error(f"RequestException during WebDriver setup for multi-city: {e}")
    except Exception as e:
        logging.error(f"An error occurred during multi-city screenshot generation: {e}", exc_info=True)
    finally:
        if driver:
            logging.info("Quitting shared WebDriver for multi-city screenshots.")
            driver.quit()

    return screenshot_paths

# Remove ImgBB upload function
# def upload_to_imgbb(image_path: str, api_key: str, expiration_seconds: int = 3600) -> str | None: ...


def post_to_instagram(local_image_path: str, caption: str, username: str, password: str) -> str | None:
    """
    Posts an image to Instagram using the instagrapi library from a local file path.

    Args:
        local_image_path (str): The local path of the image to post.
        caption (str): The caption for the Instagram post.
        username (str): Instagram username.
        password (str): Instagram password.

    Returns:
        str | None: The media ID (pk) of the post if successful, otherwise None.
    """
    if not username or not password:
        logging.error("Instagram username or password not provided. Cannot post.")
        return None

    logging.info(f"Attempting to post image from local path {local_image_path} to Instagram account {username}.")
    try:
        from instagrapi import Client
        from instagrapi.exceptions import LoginRequired, TwoFactorRequired, BadPassword
    except ImportError:
        logging.error("instagrapi library is not installed. Please install it: pip install instagrapi")
        return None

    client = Client()
    try:
        logging.info("Logging into Instagram...")
        client.login(username, password)
        logging.info("Successfully logged into Instagram.")
        logging.info(f"Uploading photo from local path: {local_image_path} with caption: '{caption[:30]}...'")
        media = client.photo_upload(path=local_image_path, caption=caption) # Changed path argument

        if media and hasattr(media, 'pk'):
            logging.info(f"Successfully posted to Instagram. Media PK: {media.pk}")
            return str(media.pk)
        else:
            logging.error("Instagram post failed. Media object was not returned or has no PK.")
            return None
    except (LoginRequired, BadPassword) as e:
        logging.error(f"Instagram login failed: {e}. Please check credentials or session. 2FA might be an issue if not handled.")
        return None
    except TwoFactorRequired as e:
        logging.error(f"Instagram login failed due to 2FA being required: {e}. The bot needs to be adapted for 2FA.")
        return None
    except Exception as e:
        logging.error(f"An error occurred during Instagram posting: {e}", exc_info=True)
        return None

def main():
    """Main function to run the Instagram bot."""
    logging.info("Instagram bot started. Initializing...")

    # --- Configuration Access and Checks ---
    # Variables are now loaded globally from .env or defaults defined above.

    # Create screenshots directory
    os.makedirs("screenshots", exist_ok=True)
    logging.info("Ensured 'screenshots' directory exists.")

    if not CITY_CODES: # This check is now against the potentially .env loaded list
        logging.error("CITY_CODES list is empty (after trying to load from .env). Please populate it. Exiting.")
        return

    # Credential checks
    # if not IMGBB_API_KEY: # Removed
    #     logging.warning("IMGBB_API_KEY is not set in .env. Image uploads will fail.")
    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        logging.warning("INSTAGRAM_USERNAME or INSTAGRAM_PASSWORD are not set in .env. Instagram posts will fail.")

    posted_invaders_log_file = "posted_invaders.csv"
    if not os.path.exists(posted_invaders_log_file):
        try:
            with open(posted_invaders_log_file, "w", encoding="utf-8") as f:
                f.write("city_code,invader_id,media_id,timestamp_utc\n")
            logging.info(f"Created posted invaders log file: {posted_invaders_log_file}")
        except IOError as e:
            logging.error(f"Failed to create posted invaders log file: {e}. Exiting.")
            return

    daily_post_count = 0

    # --- Data Extraction ---
    logging.info("Fetching and consolidating invader data...")
    data_urls = get_data_urls_from_main_page()
    if not data_urls:
        logging.error("Failed to get data URLs. Exiting.")
        return

    json_datasets = fetch_json_data(data_urls)
    if not any(json_datasets.values()):
        logging.error("Failed to fetch JSON datasets or all datasets are empty. Exiting.")
        return

    invaders_data = consolidate_data_python(json_datasets)
    if not invaders_data:
        logging.error("Failed to consolidate invader data or no data found. Exiting.")
        return
    logging.info(f"Successfully processed data for {len(invaders_data)} total invaders.")

    # --- Pre-take all screenshots ---
    logging.info("Taking screenshots for all specified cities...")
    city_screenshot_map = take_screenshots_for_cities(CITY_CODES, invaders_data, "screenshots")

    if not city_screenshot_map:
        logging.error("Failed to take any screenshots. Exiting bot run.")
        return
    logging.info(f"Screenshots taken and mapped: {city_screenshot_map}")

    # --- Main Loop through Cities ---
    for city_code_idx, city_code in enumerate(CITY_CODES):
        if daily_post_count >= DAILY_POST_LIMIT:
            logging.info(f"Daily post limit of {DAILY_POST_LIMIT} reached. Stopping further posts for today.")
            break

        logging.info(f"Processing city: {city_code.upper()} ({city_code_idx + 1}/{len(CITY_CODES)})")

        screenshot_path = city_screenshot_map.get(city_code)
        if not screenshot_path or not os.path.exists(screenshot_path):
            logging.error(f"Screenshot for {city_code.upper()} not found or path is invalid ({screenshot_path}). Skipping this city.")
            continue

        city_invader_ids = [
            inv_id for inv_id in invaders_data
            if inv_id.upper().startswith(city_code.upper() + "_")
        ]

        if not city_invader_ids:
            logging.info(f"No invaders found for city code {city_code.upper()} (data might be missing post-consolidation). Skipping.")
            continue

        logging.info(f"Found {len(city_invader_ids)} invaders for {city_code.upper()}. Using screenshot: {screenshot_path}")

        # Prepare Hashtags and Captions
        city_invader_hashtags = [f"#{inv_id.replace('_', '')}" for inv_id in city_invader_ids]
        max_hashtags_per_post = 20

        num_posts_for_city = (len(city_invader_hashtags) + max_hashtags_per_post - 1) // max_hashtags_per_post
        logging.info(f"City {city_code.upper()} will require {num_posts_for_city} post(s).")

        for i in range(num_posts_for_city):
            if daily_post_count >= DAILY_POST_LIMIT:
                logging.info(f"Daily post limit reached during segments for {city_code.upper()}.")
                break

            start_index = i * max_hashtags_per_post
            end_index = start_index + max_hashtags_per_post

            current_hashtags_segment = city_invader_hashtags[start_index:end_index]
            current_invaders_segment_ids = city_invader_ids[start_index:end_index]

            caption_text = (f"Space Invaders in {city_code.upper()}! "
                            f"Segment {i+1}/{num_posts_for_city}.\n"
                            f"{' '.join(current_hashtags_segment)}\n\n"
                            f"#SpaceInvaders #Invader #MapInvaders #{city_code.upper()}Invaders #StreetArt{city_code.upper()}")

            logging.info(f"Preparing post {i+1}/{num_posts_for_city} for {city_code.upper()} with {len(current_hashtags_segment)} invader hashtags.")

            # Upload to ImgBB - REMOVED
            # image_url = upload_to_imgbb(screenshot_path, IMGBB_API_KEY)
            # if image_url is None:
            #     logging.error(f"ImgBB upload failed for {city_code.upper()} segment {i+1}. Skipping further posts for this city.")
            #     break


            if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
                logging.error(f"Instagram credentials missing for {city_code.upper()}. Skipping actual post attempt for segment {i+1}.")
                media_id = None # Ensure media_id is None if we don't attempt
            else:
                media_id = post_to_instagram(screenshot_path, caption_text, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

            if media_id:
                logging.info(f"Successfully posted segment {i+1} for {city_code.upper()}. Media ID: {media_id}")
                daily_post_count += 1
                try:
                    with open(posted_invaders_log_file, "a", encoding="utf-8") as f_log:
                        for invader_id in current_invaders_segment_ids:
                            f_log.write(f"{city_code},{invader_id},{media_id},{datetime.utcnow().isoformat()}\n")
                    logging.info(f"Logged {len(current_invaders_segment_ids)} invaders for media ID {media_id}.")
                except IOError as e:
                    logging.error(f"Failed to write to posted invaders log: {e}")

                is_last_segment_for_city = (i == num_posts_for_city - 1)
                is_last_city = (city_code_idx == len(CITY_CODES) - 1)
                if not (is_last_segment_for_city and is_last_city) and daily_post_count < DAILY_POST_LIMIT :
                    delay_seconds = random.randint(MIN_POST_DELAY_MINUTES * 60, MAX_POST_DELAY_MINUTES * 60)
                    logging.info(f"Delaying next post by {delay_seconds // 60} minutes ({delay_seconds} seconds).")
                    time.sleep(delay_seconds)
            else:
                logging.error(f"Failed to post segment {i+1} for {city_code.upper()} to Instagram (check logs from post_to_instagram).")
                # Potentially break if a real post fails, to avoid hammering the API or if it's a persistent auth issue.
                # For now, this test will likely fail here with dummy creds, which is fine.
                # logging.warning(f"Stopping further segments for city {city_code.upper()} due to Instagram post failure.")
                # break # Uncomment if strict stop on failure is desired

            # This warning is now inside post_to_instagram or handled by the initial check
            # if i == 0 and (not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD):
            #     logging.warning(f"Instagram credentials missing, actual posting for {city_code.upper()} would fail or be skipped.")


    logging.info("Instagram bot run completed.")

if __name__ == "__main__":
    main()
