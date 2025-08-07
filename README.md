# User Agents Data

A comprehensive collection of user agent strings scraped from [useragents.me](https://useragents.me), automatically updated daily via GitHub Actions.

## 📋 Overview

This repository contains a curated collection of user agent strings organized by device type and category. The data is automatically scraped and updated daily to ensure you have access to the most current and commonly used user agents for web scraping, testing, and development purposes.

## 📁 Project Structure

```
useragents-data/
├── common/                    # Most commonly used user agents
│   ├── desktop.json          # Common desktop user agents
│   └── mobile.json           # Common mobile user agents
├── latest/                   # Latest user agents by platform
│   ├── android.json          # Latest Android user agents
│   ├── ipad.json            # Latest iPad user agents
│   ├── iphone.json          # Latest iPhone user agents
│   ├── ipod.json            # Latest iPod user agents
│   ├── linux.json           # Latest Linux user agents
│   ├── mac.json             # Latest macOS user agents
│   └── windows.json         # Latest Windows user agents
├── scraper.py               # Python scraper script
├── requirements.txt          # Python dependencies
└── .github/workflows/       # GitHub Actions automation
    └── update-useragents.yml
```

## 📊 Data Format

Each JSON file follows a consistent structure:

```json
{
  "scraped_at": "2025-08-07T12:35:58.245289Z",
  "scraped_from": "https://useragents.me",
  "type": "most_common_desktop",
  "user_agents": [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.10 Safari/605.1.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "..."
  ]
}
```

### Field Descriptions

- **`scraped_at`**: ISO 8601 timestamp when the data was scraped
- **`scraped_from`**: Source website (always `https://useragents.me`)
- **`type`**: Category identifier (e.g., `most_common_desktop`, `latest_windows`)
- **`user_agents`**: Array of user agent strings

## 🚀 Usage

### Direct Usage

You can use the JSON files directly in your projects:

```python
import json

# Load desktop user agents
with open('common/desktop.json', 'r') as f:
    desktop_data = json.load(f)
    user_agents = desktop_data['user_agents']

# Use for web scraping
import requests
headers = {'User-Agent': user_agents[0]}
response = requests.get('https://example.com', headers=headers)
```

### JavaScript/Node.js

```javascript
const fs = require("fs");

// Load mobile user agents
const mobileData = JSON.parse(fs.readFileSync("common/mobile.json", "utf8"));
const userAgents = mobileData.user_agents;

// Use in fetch requests
fetch("https://example.com", {
  headers: {
    "User-Agent": userAgents[0],
  },
});
```

### Shell Script

```bash
# Get a random desktop user agent
jq -r '.user_agents | .[0]' common/desktop.json

# Get all mobile user agents
jq -r '.user_agents[]' common/mobile.json
```

### cURL

```bash
# Use a desktop user agent with curl
curl -H "User-Agent: $(jq -r '.user_agents[0]' common/desktop.json)" https://example.com

# Use a mobile user agent with curl
curl -H "User-Agent: $(jq -r '.user_agents[0]' common/mobile.json)" https://example.com
```

## 🔧 Local Development

### Prerequisites

- Python 3.7+
- pip

### Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/useragents-data.git
cd useragents-data
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the scraper:

```bash
python scraper.py
```

### Dependencies

- `requests>=2.31.0` - HTTP library for web scraping
- `beautifulsoup4>=4.12.0` - HTML parsing
- `lxml>=4.9.0` - XML/HTML parser backend

## 🤖 Automation

This repository uses GitHub Actions to automatically update the user agent data daily at 12:00 UTC.

## 📈 Data Categories

### Common User Agents (`common/`)

- **`desktop.json`**: Most frequently used desktop browser user agents
- **`mobile.json`**: Most frequently used mobile browser user agents

### Latest User Agents (`latest/`)

- **`android.json`**: Latest Android browser user agents
- **`ipad.json`**: Latest iPad browser user agents
- **`iphone.json`**: Latest iPhone browser user agents
- **`ipod.json`**: Latest iPod browser user agents
- **`linux.json`**: Latest Linux browser user agents
- **`mac.json`**: Latest macOS browser user agents
- **`windows.json`**: Latest Windows browser user agents

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Found a bug or have a feature request? [Open an issue](https://github.com/yourusername/useragents-data/issues) or submit a pull request.

## ⚠️ Disclaimer

This data is scraped from [useragents.me](https://useragents.me) for educational and development purposes. Please respect the source website's terms of service and robots.txt when using this data.
