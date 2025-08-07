# User Agent Database

🤖 **Automated scraping of user agents from [useragents.me](https://useragents.me/)**

A Python-based scraper that extracts and organizes user agent strings from useragents.me into categorized JSON files.

## 📁 Repository Structure

```
├── common/
│   ├── desktop.json    # Most common desktop user agents
│   └── mobile.json     # Most common mobile user agents
├── latest/
│   ├── windows.json    # Latest Windows desktop user agents
│   ├── mac.json        # Latest Mac desktop user agents
│   ├── linux.json      # Latest Linux desktop user agents
│   ├── iphone.json     # Latest iPhone user agents
│   ├── ipod.json       # Latest iPod user agents
│   ├── ipad.json       # Latest iPad user agents
│   └── android.json    # Latest Android mobile user agents
├── scraper.py          # Python scraper script
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

## 📊 Data Format

Each JSON file contains a simple structure with user agent strings:

```json
{
  "scraped_at": "2025-08-07T12:35:58.245289Z",
  "scraped_from": "https://useragents.me",
  "type": "most_common_desktop",
  "user_agents": [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.10 Safari/605.1.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
  ]
}
```

### Data Structure

- `scraped_at`: ISO timestamp when the data was scraped
- `scraped_from`: Source website URL
- `type`: Category identifier (e.g., "most_common_desktop", "latest_android")
- `user_agents`: Array of user agent strings

## 🚀 Usage Examples

### JavaScript/Node.js

```javascript
// Fetch most common desktop user agents
const response = await fetch(
  "https://raw.githubusercontent.com/your-username/useragents-data/main/common/desktop.json"
);
const data = await response.json();

// Get a random desktop user agent
const randomUA =
  data.user_agents[Math.floor(Math.random() * data.user_agents.length)];
console.log(randomUA);
```

### Python

```python
import requests
import random

# Fetch latest Android user agents
response = requests.get('https://raw.githubusercontent.com/your-username/useragents-data/main/latest/android.json')
data = response.json()

# Get a random Android user agent
random_ua = random.choice(data['user_agents'])
print(random_ua)
```

### cURL

```bash
# Get most common mobile user agents
curl -s https://raw.githubusercontent.com/your-username/useragents-data/main/common/mobile.json | jq '.user_agents[]'
```

## 🛠️ Running the Scraper Locally

### Prerequisites

- Python 3.6+
- pip (Python package installer)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/useragents-data.git
cd useragents-data

# Install dependencies
pip install -r requirements.txt

# Run the scraper
python scraper.py
```

### Dependencies

- `requests>=2.31.0` - HTTP library for making requests
- `beautifulsoup4>=4.12.0` - HTML parsing library
- `lxml>=4.9.0` - XML/HTML parser backend

## 🔧 Scraper Features

The `UserAgentScraper` class provides:

- **Automatic session management** with realistic headers
- **Error handling** for network issues and parsing errors
- **Rate limiting** with small delays between requests
- **Organized output** with categorized JSON files
- **Timestamp tracking** for data freshness

### Supported Categories

**Common User Agents:**

- Desktop (most common desktop browsers)
- Mobile (most common mobile browsers)

**Latest User Agents by Platform:**

- Windows desktop
- Mac desktop
- Linux desktop
- iPhone
- iPod
- iPad
- Android mobile

## 📈 Data Categories

The scraper extracts user agents from these sections on useragents.me:

- **Most Common Desktop**: High-traffic desktop browser user agents
- **Most Common Mobile**: High-traffic mobile browser user agents
- **Latest by Platform**: Recent user agents organized by operating system/device

## ⚖️ Legal & Usage

- Data is publicly available from [useragents.me](https://useragents.me/)
- User agents are factual browser identification strings
- This repository provides organized, machine-readable access
- Perfect for web scraping, testing, and development purposes
- Please respect the source website's terms of service

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

## 🔗 Links

- **Data Source**: [useragents.me](https://useragents.me/)
- **Repository**: [GitHub](https://github.com/your-username/useragents-data)

---

**Note**: Replace `your-username` in the URLs with your actual GitHub username when using this README.
