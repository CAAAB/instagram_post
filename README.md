# Instagram Map Invaders Bot

## Overview

This bot automates the process of posting screenshots of city maps from [chborel.ch/mapinvaders](https://chborel.ch/mapinvaders) to Instagram. For each specified city, it:
1.  Extracts invader data from the website's public JSON sources.
2.  Takes a screenshot of the city's map view on `chborel.ch/mapinvaders`.
3.  Uploads the screenshot to ImgBB to get a public URL.
4.  Posts the image to a specified Instagram account.
5.  The caption includes a list of invader IDs for that city as hashtags. If the number of invaders exceeds Instagram's hashtag limit (set to 20 per post in this bot), it posts the same image multiple times with different segments of invader hashtags.
6.  Logs successfully posted invaders and their Instagram media IDs to `posted_invaders.csv`.
7.  Adheres to a daily posting limit and uses randomized delays between posts.

## Setup Instructions

### Prerequisites

*   Python 3.8 or higher.
*   An Instagram **Professional Account** (Business or Creator). The Instagram Graph API used for posting requires this.
*   An API key from [ImgBB](https://imgbb.com/api) for image hosting.

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

3.  **Configure the Bot (`instagram_bot.py`):**
    Open the `instagram_bot.py` script and fill in the following configuration variables at the top of the file:

    ```python
    # --- User Configuration ---
    CITY_CODES = ["PAR", "LDN", "NY"]  # Add your desired city codes here
    IMGBB_API_KEY = "YOUR_IMGBB_API_KEY"  # Get from https://imgbb.com/api
    INSTAGRAM_USERNAME = "YOUR_INSTAGRAM_USERNAME"
    INSTAGRAM_PASSWORD = "YOUR_INSTAGRAM_PASSWORD"

    # Optional: Adjust posting limits and delays
    # DAILY_POST_LIMIT = 20
    # MIN_POST_DELAY_MINUTES = 30
    # MAX_POST_DELAY_MINUTES = 120
    # --- End User Configuration ---
    ```
    *   `CITY_CODES`: A list of city codes (e.g., "PAR" for Paris, "ROM" for Rome) you want the bot to process.
    *   `IMGBB_API_KEY`: Your API key from ImgBB.
    *   `INSTAGRAM_USERNAME`: Your Instagram username.
    *   `INSTAGRAM_PASSWORD`: Your Instagram password.

## Running the Bot

Once configured, you can run the bot from your terminal:
```bash
python instagram_bot.py
```
The bot will start processing the cities one by one. Logs will be printed to the console.

## Output Files

*   `posted_invaders.csv`: A CSV file logging each invader that has been successfully included in an Instagram post. Columns include `city_code`, `invader_id`, `media_id`, and `timestamp_utc`.
*   `bot.log` (if file logging is explicitly configured in the script, otherwise logs to console): General operational logs.
*   `temp_city_screenshot.png`: A temporary file created for each city's screenshot. It is deleted after the city's posts are attempted.

## Important Considerations & Limitations

*   **Instagram Login:**
    *   The bot uses username/password login via the `instagrapi` library. If you have Two-Factor Authentication (2FA) enabled on your Instagram account, login might fail. You may need to handle this by:
        *   Temporarily disabling 2FA (not recommended for security).
        *   `instagrapi` might support interactive 2FA code input on the first run, or session saving/loading. Refer to `instagrapi` documentation for advanced login methods if needed.
*   **Screenshot Quality:**
    *   The bot waits for the map to load and tries to wait for invader markers to appear before taking a screenshot. However, due to the dynamic nature of the map, some screenshots might occasionally be taken before all invader markers for a city are fully visible. If this is a persistent issue, the waiting strategy in the `take_city_screenshot` function might need further refinement.
*   **API Rate Limits:**
    *   The bot respects the daily posting limit configured (`DAILY_POST_LIMIT`).
    *   Both ImgBB and Instagram have their own API rate limits. If the bot makes too many requests in a short period, it might get temporarily blocked. The randomized delays are in place to mitigate this, but be mindful if running for many cities or with very short delays.
*   **Instagram API Changes:** Instagram frequently updates its API. The `instagrapi` library attempts to keep up, but future changes could potentially break posting functionality.
*   **Error Handling:** The bot includes error handling for common issues, but unhandled exceptions might still occur. Check the console logs for details if the bot stops unexpectedly.
```
