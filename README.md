# Instagram Map Invaders Bot

## Overview

This bot automates the process of posting screenshots of city maps from [chborel.ch/mapinvaders](https://chborel.ch/mapinvaders) to Instagram. For each specified city, it:
1.  Extracts invader data from the website's public JSON sources.
2.  Takes a screenshot of the city's map view on `chborel.ch/mapinvaders`. The browser is opened once, and `navigateToCity()` JavaScript calls are used to efficiently capture all required city views.
3.  Saves the screenshot locally in the `screenshots/` directory.
4.  Posts the local image to a specified Instagram account.
5.  The caption includes a list of invader IDs for that city as hashtags. If the number of invaders exceeds Instagram's hashtag limit (set to 20 per post in this bot), it posts the same image multiple times with different segments of invader hashtags.
6.  Logs successfully posted invaders and their Instagram media IDs to `posted_invaders.csv`.
7.  Adheres to a daily posting limit and uses randomized delays between posts.

## Setup Instructions

### Prerequisites

*   Python 3.8 or higher.
*   An Instagram **Professional Account** (Business or Creator). The Instagram Graph API used for posting requires this.

### Configuration

1.  **Clone the Repository:**
    ```bash
    # If you're obtaining this from a git repository:
    # git clone <repository_url>
    # cd <repository_directory>
    ```

2.  **Install Dependencies:**
    Create a virtual environment (recommended):
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
    Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```
    (`python-dotenv` will be installed as part of this, which is used for managing environment variables).

3.  **Configure the Bot (Create `.env` file):**
    *   In the root directory of the project, you will find a file named `.env.example`. Make a copy of this file and name it `.env`.
    *   Open the `.env` file and fill in your actual credentials and desired city codes. It should look like this:

        ```env
        INSTAGRAM_USERNAME="YOUR_INSTAGRAM_USERNAME"
        INSTAGRAM_PASSWORD="YOUR_INSTAGRAM_PASSWORD"
        # Comma-separated list of city codes, e.g., PAR,ROM,LDN
        CITY_CODES="PAR,ROM,LDN"
        ```
    *   **`INSTAGRAM_USERNAME`**: Your Instagram username.
    *   **`INSTAGRAM_PASSWORD`**: Your Instagram password.
    *   **`CITY_CODES`**: A comma-separated string of city codes (e.g., "PAR" for Paris, "ROM" for Rome, "LDN" for London) you want the bot to process. Do not use spaces between codes. This is primarily used by `instagram_bot.py`.

    The bot also has other configurations like `DAILY_POST_LIMIT` directly in the `instagram_bot.py` script, which you can modify if needed. For `offline_poster.py`, some of these can also be set in the `.env` file (see specific section below).

## Running the Bot

Once configured with your `.env` file, you can run the bot from your terminal:
```bash
python instagram_bot.py
```
The bot will create a `screenshots/` directory if it doesn't exist, then start processing the cities one by one. Logs will be printed to the console.

## Output Files

*   `screenshots/`: This directory will store the screenshots taken by the bot. Filenames are in the format `citycode_invaders_count.png` (e.g., `pa_invaders_1545.png`).
*   `posted_invaders.csv`: A CSV file logging each invader that has been successfully included in an Instagram post by `instagram_bot.py`. Columns include `city_code`, `invader_id`, `media_id`, and `timestamp_utc`.
*   `bot.log` (if file logging is explicitly configured in the script, otherwise logs to console): General operational logs.


## Important Considerations & Limitations

*   **Instagram Login:**
    *   The bot uses username/password login via the `instagrapi` library. If you have Two-Factor Authentication (2FA) enabled on your Instagram account, login might fail. You may need to handle this by:
        *   Temporarily disabling 2FA (not recommended for security).
        *   `instagrapi` might support interactive 2FA code input on the first run, or session saving/loading. Refer to `instagrapi` documentation for advanced login methods if needed.
*   **Screenshot Quality:**
    *   The bot waits for the map to load and tries to wait for invader markers to appear before taking a screenshot. However, due to the dynamic nature of the map, some screenshots might occasionally be taken before all invader markers for a city are fully visible. If this is a persistent issue, the waiting strategy in the `take_screenshots_for_cities` function might need further refinement.
*   **API Rate Limits:**
    *   The bot respects the daily posting limit configured (`DAILY_POST_LIMIT`).
    *   Instagram has its own API rate limits. If the bot makes too many requests in a short period, it might get temporarily blocked. The randomized delays are in place to mitigate this, but be mindful if running for many cities or with very short delays.
*   **Instagram API Changes:** Instagram frequently updates its API. The `instagrapi` library attempts to keep up, but future changes could potentially break posting functionality.
*   **Error Handling:** The bot includes error handling for common issues, but unhandled exceptions might still occur. Check the console logs for details if the bot stops unexpectedly.

---

## Offline Instagram Poster (`offline_poster.py`)

This script provides an alternative way to post to Instagram using pre-downloaded images and a predefined list of invader IDs. It does **not** scrape any websites or take new screenshots.

### Use Case for `offline_poster.py`

Use this script if you have:
1.  A collection of images already saved in the `screenshots/` directory. Each image filename must start with the city ID prefix (e.g., `aix_myphoto.png`, `par_invaders.jpg`).
2.  A text file named `invaders.txt` in the root directory, containing a comma-separated list of all invader IDs you wish to associate with posts (e.g., `AIX_01,AIX_02,PAR_01,...`).

### How `offline_poster.py` Works

1.  Reads all invader IDs from `invaders.txt`.
2.  Groups these invader IDs by their city prefix (e.g., "AIX", "PAR").
3.  For each city:
    *   It looks for a corresponding image in the `screenshots/` directory (e.g., for "AIX", it searches for `aix_*.png` or `aix_*.jpg` etc.). It expects exactly one image per city. If no image or multiple images are found, that city is skipped, and the issue is logged in `missing_images.txt`.
    *   It then creates Instagram posts using that city's image.
    *   The caption for each post is: "🔗 Map link in bio" followed by up to 21 invader hashtags from `invaders.txt` for that city, plus a list of generic hashtags (`#mapinvaders`, `#invaderwashere`, etc.).
    *   If a city has more than 21 invader IDs, the script will post the *same city image* multiple times, each time with a different batch of 21 invader-specific hashtags, until all specified invaders for that city are covered in posts.
4.  The script uses the same Instagram credentials from your `.env` file and respects the `DAILY_POST_LIMIT`, `MIN_POST_DELAY_MINUTES`, and `MAX_POST_DELAY_MINUTES` settings (either from `.env` or defaults in the script).
5.  Successfully posted invader segments are logged to `offline_posted_log.csv`.

### Setup for `offline_poster.py`

1.  **`.env` File:** Ensure your `.env` file is configured with `INSTAGRAM_USERNAME` and `INSTAGRAM_PASSWORD` as described in the main setup section. You can also add/override `DAILY_POST_LIMIT`, `MIN_POST_DELAY_MINUTES`, `MAX_POST_DELAY_MINUTES` in the `.env` file if desired (see `.env.example` for formatting).
2.  **`invaders.txt` File:**
    *   Create a file named `invaders.txt` in the root directory of the project.
    *   Add all invader IDs you want to post, separated by commas. For example:
        ```
        AIX_01,AIX_02,AIX_03,PAR_01,PAR_02,LON_01,LON_02,LON_03,LON_04
        ```
3.  **`screenshots/` Directory:**
    *   Make sure the `screenshots/` directory exists in the root of the project.
    *   Place your pre-downloaded images here. The filename for each city's image **must** start with the city ID in lowercase, followed by an underscore (e.g., `aix_01.png`, `par_map.jpg`). The script will pick the first one it finds if multiple start with the same prefix, but it's designed with the expectation of one image per city.

### Running `offline_poster.py`

```bash
python offline_poster.py
```
Logs will be printed to the console.

### Output Files for `offline_poster.py`

*   `offline_posted_log.csv`: Logs successfully posted invader ID segments with their `media_id` and timestamp.
*   `missing_images.txt`: Lists city IDs for which a corresponding image was not found (or was ambiguous) in the `screenshots/` directory.
```
