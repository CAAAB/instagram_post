import os
import time
import random
import logging
import datetime
import csv # For robust CSV parsing
from dotenv import load_dotenv

# Attempt to import instagrapi, provide guidance if not found
try:
    from instagrapi import Client
    from instagrapi.exceptions import (
        LoginRequired, TwoFactorRequired, BadPassword,
        ClientError, ClientLoginRequired, ChallengeRequired,
        MediaNotFound
    )
except ImportError:
    print("Instagrapi library not found. Please install it using: pip install instagrapi")
    exit()

# Load environment variables from .env file
load_dotenv()

# --- Configuration (Loaded from .env or defaults) ---
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
INSTAGRAM_SESSION_FILE = "session.json" # For storing login session

# Posting parameters (can be adjusted)
DAILY_POST_LIMIT = int(os.getenv("DAILY_POST_LIMIT", "20"))
MIN_POST_DELAY_MINUTES = int(os.getenv("MIN_POST_DELAY_MINUTES", "30"))
MAX_POST_DELAY_MINUTES = int(os.getenv("MAX_POST_DELAY_MINUTES", "120"))
MAX_HASHTAGS_PER_POST = 21

BASE_CAPTION = "🔗 Map link in bio"
GENERIC_HASHTAGS = [
    "#mapinvaders", "#invaderwashere", "#spaceinvaders",
    "#spaceinvadersaroundtheworld", "#spaceinvaderwashere",
    "#flashinvaders", "#spaceinvaderaroundtheworld", "#spaceinvader",
    "#protect_them"
]

SCREENSHOTS_DIR = "screenshots/"
INVADERS_LIST_FILE = "invaders.txt"
POSTED_LOG_CSV = "offline_posted_log.csv"
MISSING_IMAGES_LOG = "missing_images.txt"
# --- End Configuration ---

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
        # logging.FileHandler("offline_bot.log") # Uncomment for file logging
    ]
)
# --- End Logging Setup ---

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

            raw_invader_ids = [inv_id.strip() for inv_id in content.split(',')]

            if not any(raw_invader_ids):
                logging.warning(f"No valid invader IDs found after parsing '{invaders_filepath}'.")
                return city_to_invaders_map

            processed_count = 0
            for invader_id_str in raw_invader_ids:
                if not invader_id_str:
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
    """
    logging.debug(f"Searching for image for city ID: {city_id} in directory: {screenshots_dir}")
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
        logging.debug(f"Found image for city {city_id}: {image_path}")
        return image_path
    elif not found_images:
        logging.warning(f"No image found for city {city_id} with prefix '{file_prefix}' in {screenshots_dir}.")
        return None
    else:
        logging.warning(f"Multiple images found for city {city_id}: {found_images}. Using the first one: {found_images[0]}.")
        return found_images[0] # Or handle ambiguity as None

def post_to_instagram_with_client(client: Client, local_image_path: str, caption: str) -> str | None:
    """
    Posts an image to Instagram using an existing instagrapi Client instance.
    """
    if not os.path.exists(local_image_path):
        logging.error(f"Local image path does not exist: {local_image_path}")
        return None

    logging.info(f"Attempting to post image from local path {local_image_path} with existing client.")
    safe_caption_preview = caption[:50].replace('\n', ' ')
    logging.info(f"Uploading photo from local path: {local_image_path} with caption: '{safe_caption_preview}...'")

    try:
        media = client.photo_upload(path=local_image_path, caption=caption)
        if media and hasattr(media, 'pk'):
            logging.info(f"Successfully posted to Instagram. Media PK: {media.pk}")
            return str(media.pk)
        else:
            logging.error("Instagram post failed. Media object was not returned or has no PK.")
            return None
    except ClientLoginRequired as e: # Session might have expired during a long run
         logging.error(f"Instagram ClientLoginRequired: {e}. Session may have expired. Re-login might be needed.")
         raise # Re-raise to be handled by the main loop
    except ChallengeRequired as e:
        logging.error(f"Instagram ChallengeRequired: {e}. Manual intervention might be needed.")
        raise
    except MediaNotFound as e: # If local_image_path is somehow invalid at upload time
        logging.error(f"Instagrapi MediaNotFound error: {e}. Check image path: {local_image_path}")
        return None
    except ClientError as e:
        logging.error(f"An Instagrapi ClientError occurred during photo upload: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during Instagram posting: {e}", exc_info=True)
        return None


def load_posted_invader_ids(csv_filepath: str) -> set:
    """Loads invader_ids from the POSTED_LOG_CSV into a set for quick lookup."""
    posted_ids = set()
    if not os.path.exists(csv_filepath):
        return posted_ids

    try:
        with open(csv_filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None) # Skip header
            if header is None or header[0] != "city_id": # Basic check for valid CSV
                logging.warning(f"{csv_filepath} is empty or has an unexpected header. Assuming no posted invaders.")
                return posted_ids

            for row in reader:
                if len(row) >= 2: # Expecting at least city_id, invader_id
                    invader_id = row[1] # invader_id is the second column
                    posted_ids.add(invader_id)
        logging.info(f"Loaded {len(posted_ids)} already posted invader IDs from {csv_filepath}.")
    except Exception as e:
        logging.error(f"Error loading posted invader IDs from {csv_filepath}: {e}", exc_info=True)
    return posted_ids

def get_posts_count_for_today(csv_filepath: str) -> int:
    """
    Counts how many posts were made today (UTC) by reading the CSV log.
    """
    count = 0
    if not os.path.exists(csv_filepath):
        return 0

    today_date = datetime.datetime.utcnow().date()
    logging.info(f"Checking for posts made on: {today_date}")

    try:
        with open(csv_filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            
            for row in reader:
                if len(row) >= 4:
                    timestamp_str = row[3]
                    try:
                        # Handle potential "Z" or microseconds variations logic if needed, 
                        # but ISO format from .isoformat() is usually standard
                        post_dt = datetime.datetime.fromisoformat(timestamp_str)
                        if post_dt.date() == today_date:
                            count += 1
                    except ValueError:
                         # Backward compatibility or malformed line
                         continue
    except Exception as e:
        logging.error(f"Error reading daily count form {csv_filepath}: {e}")
        return 0
        
    return count

def initialize_instagram_client(username, password, session_file) -> Client | None:
    """Initializes and logs into Instagram client, managing session."""
    client = Client()
    client.challenge_code_handler = lambda u, c: input(f"Enter 2FA code for {u}: ") # Basic 2FA
    # client.set_proxy("http://your_proxy_if_needed")

    if os.path.exists(session_file):
        try:
            client.load_settings(session_file)
            logging.info(f"Loaded Instagram session from {session_file}")
            # Test the session with a lightweight call
            client.get_timeline_feed()
            logging.info("Instagram session is valid.")
            return client
        except (EOFError, FileNotFoundError, Exception) as e: # Catch broad exceptions for session load issues
            logging.warning(f"Could not load session from {session_file}: {e}. Attempting full login.")
            if os.path.exists(session_file): # If file exists but is corrupt, remove it
                try:
                    os.remove(session_file)
                except OSError as ose:
                    logging.error(f"Could not remove corrupted session file {session_file}: {ose}")


    logging.info("Attempting to log into Instagram...")
    try:
        client.login(username, password)
        client.dump_settings(session_file)
        logging.info(f"Successfully logged into Instagram. Session saved to {session_file}.")
        return client
    except BadPassword:
        logging.error("Instagram login failed: BadPassword. Please check credentials.")
    except TwoFactorRequired:
        logging.error("Instagram login failed: TwoFactorRequired. Manual 2FA code entry was attempted or needs to be handled.")
        # If 2FA code was entered and login succeeded, dump_settings would have been called by Client.
        # If it failed after code entry, it might come here.
        if client.user_id: # Check if login partially succeeded (e.g. 2FA entered but next step failed)
             client.dump_settings(session_file) # Try to save what we have
             logging.info(f"Partial login state saved to {session_file} after 2FA attempt.")
        else:
             logging.error("2FA was required but could not be completed.")
    except ChallengeRequired as e:
        logging.error(f"Instagram login failed: ChallengeRequired - {e}. Account may need manual verification via browser/app.")
    except ClientLoginRequired: # Should ideally be caught by BadPassword or others, but good fallback
        logging.error("Instagram login failed: ClientLoginRequired. Session might be invalid.")
    except ClientError as e:
        logging.error(f"An Instagrapi ClientError occurred during login: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during Instagram login: {e}", exc_info=True)
    return None


def run_offline_poster():
    """Main operational function for the offline poster bot."""
    logging.info("Starting offline poster run...")

    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        logging.error("Instagram username or password not set in .env file. Exiting.")
        return

    # Initialize Instagram Client
    ig_client = initialize_instagram_client(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, INSTAGRAM_SESSION_FILE)
    if not ig_client:
        logging.error("Failed to initialize Instagram client. Exiting.")
        return

    if not os.path.exists(INVADERS_LIST_FILE):
        logging.error(f"Invaders list file not found: {INVADERS_LIST_FILE}. Please create it. Exiting.")
        return
    if not os.path.exists(SCREENSHOTS_DIR):
        logging.error(f"Screenshots directory '{SCREENSHOTS_DIR}' does not exist. Please create it. Exiting.")
        return
    if not os.listdir(SCREENSHOTS_DIR) and os.path.exists(SCREENSHOTS_DIR):
         logging.warning(f"Screenshots directory '{SCREENSHOTS_DIR}' exists but is empty.")

         logging.warning(f"Screenshots directory '{SCREENSHOTS_DIR}' exists but is empty.")

    daily_post_count = get_posts_count_for_today(POSTED_LOG_CSV)
    logging.info(f"Posts already made today: {daily_post_count}. Daily limit is: {DAILY_POST_LIMIT}")
    try:
        with open(MISSING_IMAGES_LOG, 'w', encoding='utf-8') as f: f.write("")
        logging.info(f"Initialized/Cleared {MISSING_IMAGES_LOG}")
    except IOError as e:
        logging.error(f"Could not initialize {MISSING_IMAGES_LOG}: {e}")

    if not os.path.exists(POSTED_LOG_CSV):
        try:
            with open(POSTED_LOG_CSV, 'w', encoding='utf-8', newline='') as f: # Add newline='' for csv
                writer = csv.writer(f)
                writer.writerow(["city_id", "invader_id", "media_id", "timestamp_utc"])
            logging.info(f"Created {POSTED_LOG_CSV} with header.")
        except IOError as e:
            logging.error(f"Could not create {POSTED_LOG_CSV}: {e}")
            return

    # Load already posted invader IDs
    posted_invader_ids = load_posted_invader_ids(POSTED_LOG_CSV)

    city_to_invaders_map = load_and_group_invaders(INVADERS_LIST_FILE)
    if not city_to_invaders_map:
        logging.error(f"No invaders loaded from {INVADERS_LIST_FILE}. Exiting.")
        return

    logging.info(f"Loaded invaders for {len(city_to_invaders_map)} cities.")

    city_keys = list(city_to_invaders_map.keys())
    for city_idx, city_id in enumerate(city_keys):
        all_invader_ids_for_city = city_to_invaders_map[city_id]

        if daily_post_count >= DAILY_POST_LIMIT:
            logging.info(f"Daily post limit of {DAILY_POST_LIMIT} reached. Stopping before processing {city_id}.")
            break # Use break to exit the city loop

        logging.info(f"--- Processing city: {city_id} ({city_idx + 1}/{len(city_keys)}) ---")

        local_image_path = find_city_image(city_id, SCREENSHOTS_DIR)
        if local_image_path is None:
            logging.warning(f"Image for {city_id} not found or ambiguous. Skipping.")
            try:
                with open(MISSING_IMAGES_LOG, 'a', encoding='utf-8') as f_miss:
                    f_miss.write(f"{datetime.datetime.utcnow().isoformat()},{city_id}\n")
            except IOError as e:
                logging.error(f"Could not write to {MISSING_IMAGES_LOG}: {e}")
            continue

        # Filter out already posted invaders for this city before segmentation
        invader_ids_to_process_for_city = [
            inv_id for inv_id in all_invader_ids_for_city if inv_id not in posted_invader_ids
        ]

        if not invader_ids_to_process_for_city:
            logging.info(f"All invaders for city {city_id} have already been posted. Skipping city.")
            continue

        logging.info(f"City {city_id}: {len(invader_ids_to_process_for_city)} new invaders to post (out of {len(all_invader_ids_for_city)} total).")

        invader_specific_hashtags = [f"#{inv_id}" for inv_id in invader_ids_to_process_for_city]
        num_posts_for_city = (len(invader_specific_hashtags) + MAX_HASHTAGS_PER_POST - 1) // MAX_HASHTAGS_PER_POST
        logging.info(f"City {city_id} requires {num_posts_for_city} post(s) for its new invaders.")

        for i in range(num_posts_for_city):
            if daily_post_count >= DAILY_POST_LIMIT:
                logging.info(f"Daily post limit of {DAILY_POST_LIMIT} reached during segments for {city_id}. Stopping city processing.")
                break # Break from segment loop for this city

            start_index = i * MAX_HASHTAGS_PER_POST
            end_index = start_index + MAX_HASHTAGS_PER_POST

            # These are the invader IDs for THIS specific post segment
            current_segment_invader_ids = invader_ids_to_process_for_city[start_index:end_index]
            current_segment_hashtags = [f"#{inv_id}" for inv_id in current_segment_invader_ids]

            if not current_segment_invader_ids: # Should not happen if num_posts_for_city is calculated correctly
                logging.warning(f"Segment {i+1}/{num_posts_for_city} for {city_id} has no new invaders. Skipping.")
                continue

            caption_parts = [BASE_CAPTION]
            caption_parts.extend(current_segment_hashtags)
            caption_parts.extend(GENERIC_HASHTAGS[:8]) # Adjust as needed
            caption_text = " ".join(caption_parts)
            safe_caption_log_preview = caption_text[:100].replace('\n',' ')
            logging.info(f"Posting segment {i+1}/{num_posts_for_city} for {city_id} with {len(current_segment_invader_ids)} new invaders. Caption: '{safe_caption_log_preview}...'")

            media_id = None
            try:
                media_id = post_to_instagram_with_client(ig_client, local_image_path, caption_text)
            except (ClientLoginRequired, ChallengeRequired) as e:
                logging.error(f"Critical Instagram API error during post: {e}. Attempting to re-initialize client for next run if any.")
                # Attempt re-login for the *next* potential post (might not happen in this run)
                ig_client = initialize_instagram_client(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, INSTAGRAM_SESSION_FILE)
                if not ig_client:
                    logging.error("Failed to re-initialize Instagram client after error. Exiting.")
                    return # Exit entirely
                # If re-initialization worked, the current post still failed.
                logging.error(f"Failed to post segment {i+1}/{num_posts_for_city} for {city_id} due to session/challenge issue. Skipping segment.")
                # Potentially break city or even entire run depending on severity
                break # Break from this city's segments
            except Exception as e: # Catch any other unexpected error from post_to_instagram_with_client
                logging.error(f"Unexpected error calling post_to_instagram_with_client: {e}. Skipping segment.")
                break # Break from this city's segments


            if media_id:
                logging.info(f"Successfully posted segment {i+1}/{num_posts_for_city} for {city_id}. Media ID: {media_id}")
                daily_post_count += 1
                try:
                    with open(POSTED_LOG_CSV, 'a', encoding='utf-8', newline='') as f_log:
                        writer = csv.writer(f_log)
                        for inv_id in current_segment_invader_ids: # Log only newly posted invader IDs
                            writer.writerow([city_id, inv_id, media_id, datetime.datetime.utcnow().isoformat()])
                            posted_invader_ids.add(inv_id) # Update in-memory set
                    logging.info(f"Logged {len(current_segment_invader_ids)} posted invaders to {POSTED_LOG_CSV}.")
                except IOError as e:
                    logging.error(f"Could not write to {POSTED_LOG_CSV}: {e}")

                is_last_segment_for_city = (i == num_posts_for_city - 1)
                is_last_city_overall = (city_idx == len(city_keys) - 1)

                if not (is_last_segment_for_city and is_last_city_overall):
                    if daily_post_count < DAILY_POST_LIMIT:
                        delay_seconds = random.randint(MIN_POST_DELAY_MINUTES * 60, MAX_POST_DELAY_MINUTES * 60)
                        logging.info(f"Waiting for {delay_seconds // 60} minutes ({delay_seconds} seconds) before next post.")
                        time.sleep(delay_seconds)
            else:
                logging.error(f"Failed to post segment {i+1}/{num_posts_for_city} for {city_id}. Skipping remaining segments for this city.")
                break # Break from segment loop for this city
        # End of segment loop for a city
    # End of city loop
    logging.info("Offline poster run completed.")

if __name__ == "__main__":
    run_offline_poster()