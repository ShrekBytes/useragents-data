# User Agent Database

🤖 **Automated daily updates of the most current and common user agents from [useragents.me](https://useragents.me/)**


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
│   ├── android.json    # Latest Android mobile user agents
│   └── tablet.json     # Latest tablet user agents
└── scraper.py          # Python scraper script
```

## 📊 Data Format

Each JSON file contains:

```json
{
  "scraped_at": "2025-08-07T12:35:58.245289Z",
  "scraped_from": "https://useragents.me",
  "type": "most_common_desktop",
  "user_agents": [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.10 Safari/605.1.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.3",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Trailer/93.3.8652.5",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 OPR/117.0.0.",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36 Edge/18.1958",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.3"
  ]
}
```

### Common User Agents Format
- `user_agent`: The actual user agent string
- `share_percentage`: Percentage share in web traffic
- `browser_info`: Browser and OS information
- `device`: Device type (mobile only)

### Latest User Agents Format
- `user_agent`: The actual user agent string
- `browser_info`: Browser and OS information
- `device`: Device type (mobile categories only)

## 🔄 Update Schedule

- **Automatic updates**: Daily at 12:00 UTC via GitHub Actions
- **Manual updates**: Can be triggered manually from the Actions tab
- **Source monitoring**: Updates when scraper code changes

## 🚀 Usage Examples

### JavaScript/Node.js
```javascript
// Fetch most common desktop user agents
const response = await fetch('https://raw.githubusercontent.com/ShrekBytes/user-agent-database/main/common/desktop.json');
const data = await response.json();

// Get a random desktop user agent
const randomUA = data.user_agents[Math.floor(Math.random() * data.user_agents.length)];
console.log(randomUA.user_agent);
```

### Python
```python
import requests
import random

# Fetch latest Android user agents
response = requests.get('https://raw.githubusercontent.com/ShrekBytes/user-agent-database/main/latest/android.json')
data = response.json()

# Get a random Android user agent
random_ua = random.choice(data['user_agents'])
print(random_ua['user_agent'])
```

### cURL
```bash
# Get most common mobile user agents
curl -s https://raw.githubusercontent.com/ShrekBytes/user-agent-database/main/common/mobile.json | jq '.user_agents[]'
```

## 📈 Statistics

The database contains user agents categorized by:
- **Most Common**: Based on actual web traffic analysis
- **Latest**: Most recent user agent strings by platform
- **Desktop**: Windows, Mac, Linux
- **Mobile**: iPhone, iPad, iPod, Android
- **Tablets**: Cross-platform tablet user agents

## 🛠️ Running the Scraper Locally

```bash
# Clone the repository
git clone https://github.com/ShrekBytes/user-agent-database.git
cd user-agent-database

# Install dependencies
pip install requests beautifulsoup4

# Run the scraper
python scraper.py
```

## ⚖️ Legal & Usage

- Data is publicly available from [useragents.me](https://useragents.me/)
- User agents are factual browser identification strings
- This repository provides organized, machine-readable access
- Perfect for web scraping, testing, and development purposes

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

## 🔗 Links

- **Data Source**: [useragents.me](https://useragents.me/)

---

**Last Updated**: Automatically updated daily by GitHub Actions 🤖
