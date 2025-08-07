# User Agent Scraper

This project automatically scrapes the most common desktop and mobile user agents from [useragents.me](https://www.useragents.me) and updates JSON files in this repository every 24 hours.

## Files

- `common-desktop.json` - Most common desktop user agents
- `common-mobile.json` - Most common mobile user agents
- `scraper.py` - Python scraping script
- `requirements.txt` - Python dependencies
- `.github/workflows/scrape-useragents.yml` - GitHub Actions workflow

## Setup Instructions

1. **Create a new GitHub repository**
2. **Add the following files to your repository:**

### File: `scraper.py`
```python
# Copy the content from the scraper script artifact
```

### File: `requirements.txt`
```
requests==2.31.0
beautifulsoup4==4.12.3
lxml==4.9.4
```

### File: `.github/workflows/scrape-useragents.yml`
```yaml
# Copy the content from the GitHub workflow artifact
```

3. **Initial Setup**
   - Commit and push all files to your repository
   - Go to the Actions tab in your GitHub repository
   - You should see the "User Agent Scraper" workflow

4. **Manual Trigger (Optional)**
   - Go to Actions tab → User Agent Scraper workflow
   - Click "Run workflow" to test it manually
   - This will create the initial JSON files

## How it Works

- **Automated Schedule**: Runs daily at 2 AM UTC
- **Manual Trigger**: Can be triggered manually from GitHub Actions
- **Respectful Scraping**: Includes delays and proper headers
- **Error Handling**: Comprehensive logging and error handling
- **Conditional Commits**: Only commits when data actually changes

## Output Files Structure

### common-desktop.json
```json
{
  "scraped_at": "2025-01-09T02:00:00Z",
  "source": "https://www.useragents.me",
  "user_agents": [
    {
      "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
      "pct": 17.34
    }
  ]
}
```

### common-mobile.json
```json
{
  "scraped_at": "2025-01-09T02:00:00Z",
  "source": "https://www.useragents.me", 
  "user_agents": [
    {
      "ua": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36...",
      "pct": 63.11
    }
  ]
}
```

## Usage

### JavaScript Example
```javascript
// Fetch desktop user agents
const response = await fetch('https://raw.githubusercontent.com/yourusername/yourrepo/main/common-desktop.json');
const data = await response.json();
const userAgents = data.user_agents;

// Get a random user agent
const randomUA = userAgents[Math.floor(Math.random() * userAgents.length)].ua;
```

### Python Example
```python
import requests
import random

# Fetch mobile user agents
response = requests.get('https://raw.githubusercontent.com/yourusername/yourrepo/main/common-mobile.json')
data = response.json()
user_agents = data['user_agents']

# Get a random user agent
random_ua = random.choice(user_agents)['ua']
```

## Features

- ✅ Automated daily scraping
- ✅ Respectful rate limiting
- ✅ Comprehensive error handling
- ✅ Structured JSON output with metadata
- ✅ Only commits when data changes
- ✅ Easy to use via raw GitHub URLs

## Monitoring

Check the Actions tab in your repository to monitor scraping runs. Each run will show:
- Number of user agents scraped
- Success/failure status
- Commit messages with timestamps

## Customization

- **Change schedule**: Edit the cron expression in `.github/workflows/scrape-useragents.yml`
- **Add more data**: Modify `scraper.py` to extract additional sections
- **Change file names**: Update the script and workflow to use different output file names