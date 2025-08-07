#!/usr/bin/env python3
"""
User Agent Scraper for useragents.me
Scrapes and saves user agents in simple JSON format
"""

import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import time

class UserAgentScraper:
    def __init__(self):
        self.base_url = "https://useragents.me"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
        })
        
    def scrape_page(self):
        """Scrape the main useragents.me page"""
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            print(f"Error scraping page: {e}")
            return None
    
    def extract_common_desktop(self, soup):
        """Extract most common desktop user agents"""
        try:
            # Find the desktop section
            desktop_section = soup.find('h2', id='most-common-desktop-useragents')
            if not desktop_section:
                return []
            
            # Find the table after this section
            table = desktop_section.find_next('table')
            if not table:
                return []
            
            user_agents = []
            rows = table.find('tbody').find_all('tr')
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    ua_textarea = cells[2].find('textarea')
                    if ua_textarea:
                        user_agent = ua_textarea.get_text(strip=True)
                        if user_agent and user_agent not in user_agents:
                            user_agents.append(user_agent)
            
            return user_agents
        except Exception as e:
            print(f"Error extracting desktop user agents: {e}")
            return []
    
    def extract_common_mobile(self, soup):
        """Extract most common mobile user agents"""
        try:
            # Find the mobile section
            mobile_section = soup.find('h2', id='most-common-mobile-useragents')
            if not mobile_section:
                return []
            
            # Find the table after this section
            table = mobile_section.find_next('table')
            if not table:
                return []
            
            user_agents = []
            rows = table.find('tbody').find_all('tr')
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 4:
                    ua_textarea = cells[3].find('textarea')
                    if ua_textarea:
                        user_agent = ua_textarea.get_text(strip=True)
                        if user_agent and user_agent not in user_agents:
                            user_agents.append(user_agent)
            
            return user_agents
        except Exception as e:
            print(f"Error extracting mobile user agents: {e}")
            return []
    
    def extract_latest_by_section(self, soup, section_id):
        """Extract latest user agents by section ID"""
        try:
            section = soup.find('h2', id=section_id)
            if not section:
                return []
            
            table = section.find_next('table')
            if not table:
                return []
            
            user_agents = []
            tbody = table.find('tbody')
            if not tbody:
                return []
                
            rows = tbody.find_all('tr')
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 2:
                    # Find textarea in the last cell
                    ua_textarea = cells[-1].find('textarea')
                    if ua_textarea:
                        user_agent = ua_textarea.get_text(strip=True)
                        if user_agent and user_agent not in user_agents:
                            user_agents.append(user_agent)
            
            return user_agents
        except Exception as e:
            print(f"Error extracting latest user agents for {section_id}: {e}")
            return []
    
    def save_json(self, user_agents, filepath, ua_type):
        """Save user agents to JSON file"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Create simple JSON structure
            data = {
                "scraped_at": datetime.utcnow().isoformat() + "Z",
                "scraped_from": self.base_url,
                "type": ua_type,
                "user_agents": user_agents
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"Saved {len(user_agents)} user agents to {filepath}")
            return True
        except Exception as e:
            print(f"Error saving {filepath}: {e}")
            return False
    
    def run(self):
        """Main scraping function"""
        print("Starting user agent scraping...")
        
        # Scrape the main page
        soup = self.scrape_page()
        if not soup:
            print("Failed to scrape main page")
            return False
        
        success_count = 0
        
        # Extract and save common desktop user agents
        desktop_agents = self.extract_common_desktop(soup)
        if desktop_agents:
            if self.save_json(desktop_agents, "common/desktop.json", "most_common_desktop"):
                success_count += 1
        
        # Extract and save common mobile user agents
        mobile_agents = self.extract_common_mobile(soup)
        if mobile_agents:
            if self.save_json(mobile_agents, "common/mobile.json", "most_common_mobile"):
                success_count += 1
        
        # Extract latest user agents by category
        latest_sections = {
            "latest-windows-desktop-useragents": ("latest/windows.json", "latest_windows"),
            "latest-mac-desktop-useragents": ("latest/mac.json", "latest_mac"),
            "latest-linux-desktop-useragents": ("latest/linux.json", "latest_linux"),
            "latest-iphone-useragents": ("latest/iphone.json", "latest_iphone"),
            "latest-ipod-useragents": ("latest/ipod.json", "latest_ipod"),
            "latest-ipad-useragents": ("latest/ipad.json", "latest_ipad"),
            "latest-android-mobile-useragents": ("latest/android.json", "latest_android"),
            "latest-tablet-useragents": ("latest/tablet.json", "latest_tablet")
        }
        
        for section_id, (filepath, ua_type) in latest_sections.items():
            agents = self.extract_latest_by_section(soup, section_id)
            if agents:
                if self.save_json(agents, filepath, ua_type):
                    success_count += 1
            # Small delay between requests
            time.sleep(0.1)
        
        print(f"Scraping completed! Successfully created {success_count} files.")
        return success_count > 0

if __name__ == "__main__":
    scraper = UserAgentScraper()
    success = scraper.run()
    exit(0 if success else 1)