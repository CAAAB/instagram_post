import os
import time
import random
import logging
import datetime
from dotenv import load_dotenv

# Attempt to import instagrapi, provide guidance if not found
try:
    from instagrapi import Client
    from instagrapi.exceptions import LoginRequired, TwoFactorRequired, BadPassword, ClientError, ClientLoginRequired
except ImportError:
    print("Instagrapi library not found. Please install it using: pip install instagrapi")
    # If running in an environment where exit() is problematic, raise an exception or log critical error.
    # For now, simple print and exit for command-line use.
    exit()

# Load environment variables from .env file
load_dotenv()

# --- Configuration (Loaded from .env or defaults) ---
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

# Posting parameters (can be adjusted)
DAILY_POST_LIMIT = int(os.getenv("DAILY_POST_LIMIT", "20")) # Original
MIN_POST_DELAY_MINUTES = int(os.getenv("MIN_POST_DELAY_MINUTES", "30"))
MAX_POST_DELAY_MINUTES = int(os.getenv("MAX_POST_DELAY_MINUTES", "120"))
MAX_HASHTAGS_PER_POST = 21 # Max 30 total, using 21 for invader tags to leave room for generic ones

BASE_CAPTION = "🔗 Map link in bio" # General part of the caption
GENERIC_HASHTAGS = [
    "#mapinvaders", "#invaderwashere", "#spaceinvaders",
    "#spaceinvadersaroundtheworld", "#spaceinvaderwashere",
    "#flashinvaders", "#spaceinvaderaroundtheworld", "#spaceinvader",
    "#protect_them"
] # General hashtags to add to each post

SCREENSHOTS_DIR = "screenshots/" # Directory where city screenshots are stored
INVADERS_LIST_FILE = "invaders.txt" # File containing comma-separated invader IDs
POSTED_LOG_CSV = "offline_posted_log.csv" # Log of successfully posted invaders by this script
MISSING_IMAGES_LOG = "missing_images.txt" # Log for cities where images couldn't be found
# --- End Configuration ---

# --- Logging Setup ---
# Basic configuration, can be expanded (e.g., to include file logging)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler() # Log to console
        # You can add logging.FileHandler("offline_bot.log") here if needed
    ]
)
# --- End Logging Setup ---

# Function stubs (to be implemented in later steps)
def load_and_group_invaders(invaders_filepath: str) -> dict:
    """
    Loads invader IDs from the specified file and groups them by city ID.
    Expected format in file: comma-separated invader IDs (e.g., PA_01,PA_02,LDN_01).
    """
    logging.info(f"Attempting to load invader list from: {invaders_filepath}")
    city_to_invaders_map = {}

    try:
        with open(invaders_filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content.strip():
                logging.warning(f"Invaders file '{invaders_filepath}' is empty.")
                return city_to_invaders_map

            # Split by comma, then strip whitespace from each potential ID
            raw_invader_ids = [inv_id.strip() for inv_id in content.split(',')]

            if not any(raw_invader_ids): # Check if all items are empty strings after strip
                logging.warning(f"No valid invader IDs found after parsing '{invaders_filepath}'.")
                return city_to_invaders_map

            processed_count = 0
            for invader_id_str in raw_invader_ids:
                if not invader_id_str: # Skip if the string is empty after strip
                    continue

                parts = invader_id_str.split('_')
                if len(parts) < 2 or not parts[0]:
                    logging.warning(f"Malformed invader ID '{invader_id_str}' found in '{invaders_filepath}'. Skipping.")
                    continue

                city_prefix = parts[0].upper()

                if city_prefix not in city_to_invaders_map:
                    city_to_invaders_map[city_prefix] = []

                city_to_invaders_map[city_prefix].append(invader_id_str)
                processed_count += 1

            if processed_count > 0:
                logging.info(f"Successfully processed {processed_count} invader IDs into {len(city_to_invaders_map)} cities.")
            else:
                logging.warning(f"No processable invader IDs found in '{invaders_filepath}' despite file not being empty.")

    except FileNotFoundError:
        logging.error(f"Invaders file not found: {invaders_filepath}")
    except Exception as e:
        logging.error(f"An error occurred while loading invaders from '{invaders_filepath}': {e}", exc_info=True)

    return city_to_invaders_map

def find_city_image(city_id: str, screenshots_dir: str) -> str | None:
    """
    Finds the screenshot file for a given city_id in the screenshots_dir.
    The filename is expected to be like 'cityid_invaders_count.png' or similar.
    This function will find any file starting with 'cityid_'.
    """
    logging.info(f"Searching for image for city ID: {city_id} in directory: {screenshots_dir}")

    if not os.path.isdir(screenshots_dir):
        logging.error(f"Screenshots directory not found: {screenshots_dir}")
        return None

    file_prefix = city_id.lower() + "_"
    found_images = []

    for filename in os.listdir(screenshots_dir):
        if filename.lower().startswith(file_prefix):
            found_images.append(os.path.join(screenshots_dir, filename))

    if len(found_images) == 1:
        image_path = found_images[0]
        logging.info(f"Found image for city {city_id}: {image_path}")
        return image_path
    elif len(found_images) == 0:
        logging.warning(f"No image found for city {city_id} with prefix '{file_prefix}' in {screenshots_dir}.")
        return None
    else: # len(found_images) > 1
        logging.warning(f"Multiple images found for city {city_id} with prefix '{file_prefix}' in {screenshots_dir}: {found_images}")
        logging.warning("Returning None due to ambiguity. Please ensure only one image per city prefix or refine selection logic.")
        return None # Or could decide to return found_images[0] by default if preferred

# Re-using the post_to_instagram function from instagram_bot.py
# (Copied and pasted, then potentially adapted if needed for offline script specifics)
def post_to_instagram(local_image_path: str, caption: str, username: str, password: str) -> str | None:
    """
    Posts an image to Instagram using the instagrapi library from a local file path.
    """
    # Original logic starts here
    if not username or not password: # Should be checked before calling ideally
        logging.error("Instagram username or password not provided to post_to_instagram function.")
        return None
    if not os.path.exists(local_image_path):
        logging.error(f"Local image path does not exist: {local_image_path}")
        return None

    logging.info(f"Attempting to post image from local path {local_image_path} to Instagram account {username}.")

    client = Client()
    # Example: client.set_proxy("http://your_proxy_if_needed")
    # Example: client.load_settings('session.json') # For session persistence

    try:
        logging.info("Logging into Instagram...")
        client.login(username, password)
        logging.info("Successfully logged into Instagram.")

        # Example: client.dump_settings('session.json') # Save session after successful login

        safe_caption_preview = caption[:50].replace('\n', ' ')
        logging.info(f"Uploading photo from local path: {local_image_path} with caption: '{safe_caption_preview}...'")
        media = client.photo_upload(path=local_image_path, caption=caption)

        if media and hasattr(media, 'pk'):
            logging.info(f"Successfully posted to Instagram. Media PK: {media.pk}")
            return str(media.pk)
        else:
            logging.error("Instagram post failed. Media object was not returned or has no PK.")
            return None

    except BadPassword as e:
        logging.error(f"Instagram login failed: BadPassword - {e}. Please check credentials.")
        return None
    except TwoFactorRequired as e:
        logging.error(f"Instagram login failed: TwoFactorRequired - {e}. Bot needs 2FA handling or use device password / load session.")
        return None
    except LoginRequired as e: # Should ideally be caught by BadPassword or others, but good fallback
        logging.error(f"Instagram login failed: LoginRequired - {e}. Session might be invalid.")
        return None
    except ClientLoginRequired as e: # Instagrapi can raise this too
         logging.error(f"Instagram ClientLoginRequired: {e}. Session may have expired or been invalidated.")
         return None
    except ClientError as e: # Catch other instagrapi client errors
        logging.error(f"An Instagrapi ClientError occurred: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during Instagram posting: {e}", exc_info=True)
        return None
    # finally:
    #     # Consider if client.logout() is needed or if sessions are managed externally
    #     # logging.info("Logging out from Instagram.")
    #     # client.logout() # Usually not required if you plan to reuse session or run often

def run_offline_poster():
    """
    Main operational function for the offline poster bot.
    """
    logging.info("Starting offline poster run...")

    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        logging.error("Instagram username or password not set in .env file. Exiting.")
        return

    if not os.path.exists(INVADERS_LIST_FILE):
        logging.error(f"Invaders list file not found: {INVADERS_LIST_FILE}. Please create it. Exiting.")
        return

    # This check might be redundant if the test setup above always creates the dir.
    # However, good for production when test setup is removed.
    if not os.path.exists(SCREENSHOTS_DIR): # Check if dir itself exists
        logging.error(f"Screenshots directory '{SCREENSHOTS_DIR}' does not exist. Please create it. Exiting.")
        return
    # Warning if it exists but is empty (might be legitimate if no screenshots processed yet by main bot)
    if not os.listdir(SCREENSHOTS_DIR) and os.path.exists(SCREENSHOTS_DIR):
         logging.warning(f"Screenshots directory '{SCREENSHOTS_DIR}' exists but is empty.")


    # Initialize or load daily post count
    daily_post_count = 0

    # Create/clear MISSING_IMAGES_LOG
    try:
        with open(MISSING_IMAGES_LOG, 'w', encoding='utf-8') as f:
            f.write("") # Clear or create the log
        logging.info(f"Initialized/Cleared {MISSING_IMAGES_LOG}")
    except IOError as e:
        logging.error(f"Could not initialize {MISSING_IMAGES_LOG}: {e}")
        # Decide if this is fatal; for now, continue

    # Initialize POSTED_LOG_CSV with header if it doesn't exist
    if not os.path.exists(POSTED_LOG_CSV):
        try:
            with open(POSTED_LOG_CSV, 'w', encoding='utf-8') as f:
                f.write("city_id,invader_id,media_id,timestamp_utc\n")
            logging.info(f"Created {POSTED_LOG_CSV} with header.")
        except IOError as e:
            logging.error(f"Could not create {POSTED_LOG_CSV}: {e}")
            return # This might be considered fatal

    # Load Invaders
    city_to_invaders_map = load_and_group_invaders(INVADERS_LIST_FILE)
    if not city_to_invaders_map:
        logging.error(f"No invaders loaded from {INVADERS_LIST_FILE}. Exiting.")
        return

    logging.info(f"Loaded invaders for {len(city_to_invaders_map)} cities: {list(city_to_invaders_map.keys())}")
    for city_id_key, invader_list_val in city_to_invaders_map.items():
            logging.info(f"City {city_id_key}: {len(invader_list_val)} invaders")


    # Main City Loop
    city_keys = list(city_to_invaders_map.keys()) # Get a list of keys to know the last city
    for city_idx, city_id in enumerate(city_keys):
        invader_ids_for_city = city_to_invaders_map[city_id]

        if daily_post_count >= DAILY_POST_LIMIT: # Check before processing each new city
            logging.info(f"Daily post limit of {DAILY_POST_LIMIT} reached. Stopping before processing {city_id}.")
            return

        logging.info(f"--- Processing city: {city_id} ({city_idx + 1}/{len(city_keys)}) ---")

        local_image_path = find_city_image(city_id, SCREENSHOTS_DIR)
        if local_image_path is None:
            logging.warning(f"Image for {city_id} not found or ambiguous. Skipping.")
            try:
                with open(MISSING_IMAGES_LOG, 'a', encoding='utf-8') as f_miss:
                    f_miss.write(f"{datetime.datetime.utcnow().isoformat()},{city_id}\n")
            except IOError as e:
                logging.error(f"Could not write to {MISSING_IMAGES_LOG}: {e}")
            continue # Move to the next city

        invader_specific_hashtags = [f"#{inv_id.replace('_', '')}" for inv_id in invader_ids_for_city]
        num_posts_for_city = (len(invader_specific_hashtags) + MAX_HASHTAGS_PER_POST - 1) // MAX_HASHTAGS_PER_POST
        logging.info(f"City {city_id} requires {num_posts_for_city} post(s) for {len(invader_ids_for_city)} invaders.")

        # Segment Posting Loop
        for i in range(num_posts_for_city):
            if daily_post_count >= DAILY_POST_LIMIT:
                logging.info(f"Daily post limit of {DAILY_POST_LIMIT} reached during segments for {city_id}. Stopping.")
                return # End all processing

            start_index = i * MAX_HASHTAGS_PER_POST
            end_index = start_index + MAX_HASHTAGS_PER_POST
            current_invader_hashtags_segment = invader_specific_hashtags[start_index:end_index]
            current_invader_ids_segment = invader_ids_for_city[start_index:end_index]

            caption_parts = [BASE_CAPTION]
            caption_parts.extend(current_invader_hashtags_segment)
            # Add some generic hashtags, ensuring total doesn't exceed Instagram limits (approx 30)
            # Max 21 invader tags + BASE_CAPTION leaves room for about 8 generic.
            caption_parts.extend(GENERIC_HASHTAGS[:8])
            caption_text = " ".join(caption_parts)

            safe_caption_log_preview = caption_text[:100].replace('\n',' ')
            logging.info(f"Posting segment {i+1}/{num_posts_for_city} for {city_id}. Caption: '{safe_caption_log_preview}...'")

            if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
                logging.error(f"Instagram credentials missing. Cannot post segment {i+1} for {city_id}. Skipping city.")
                break # Skip remaining segments for this city

            media_id = post_to_instagram(local_image_path, caption_text, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

            if media_id:
                logging.info(f"Successfully posted segment {i+1}/{num_posts_for_city} for {city_id}. Media ID: {media_id}")
                daily_post_count += 1
                try:
                    with open(POSTED_LOG_CSV, 'a', encoding='utf-8') as f_log:
                        for inv_id in current_invader_ids_segment:
                            f_log.write(f"{city_id},{inv_id},{media_id},{datetime.datetime.utcnow().isoformat()}\n")
                    logging.info(f"Logged {len(current_invader_ids_segment)} posted invaders to {POSTED_LOG_CSV}.")
                except IOError as e:
                    logging.error(f"Could not write to {POSTED_LOG_CSV}: {e}")

                # Delay logic
                is_last_segment_for_city = (i == num_posts_for_city - 1)
                is_last_city_overall = (city_idx == len(city_keys) - 1)

                if not (is_last_segment_for_city and is_last_city_overall):
                    if daily_post_count < DAILY_POST_LIMIT: # Only sleep if more posts are allowed today
                        delay_seconds = random.randint(MIN_POST_DELAY_MINUTES * 60, MAX_POST_DELAY_MINUTES * 60)
                        logging.info(f"Waiting for {delay_seconds // 60} minutes ({delay_seconds} seconds) before next post.")
                        time.sleep(delay_seconds)
                    # else: (daily limit reached, will be caught at the start of the next loop iteration)
                # else: (this was the very last invader segment of the very last city)

            else: # media_id is None (post failed)
                logging.error(f"Failed to post segment {i+1}/{num_posts_for_city} for {city_id}. Skipping remaining segments for this city.")
                break # Break from segment loop for this city

    logging.info("Offline poster run completed.")


if __name__ == "__main__":
    run_offline_poster()
