#!/usr/bin/env python3
"""
User Agent Scraper for useragents.me
Scrapes and saves user agents in organized JSON format
"""

import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import re
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
                    share = cells[0].get_text(strip=True)
                    browser_info = cells[1].get_text(strip=True)
                    ua_textarea = cells[2].find('textarea')
                    
                    if ua_textarea:
                        user_agent = ua_textarea.get_text(strip=True)
                        user_agents.append({
                            "user_agent": user_agent,
                            "share_percentage": float(share) if share.replace('.', '').isdigit() else 0,
                            "browser_info": browser_info
                        })
            
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
                    share = cells[0].get_text(strip=True)
                    device = cells[1].get_text(strip=True)
                    browser_info = cells[2].get_text(strip=True)
                    ua_textarea = cells[3].find('textarea')
                    
                    if ua_textarea:
                        user_agent = ua_textarea.get_text(strip=True)
                        user_agents.append({
                            "user_agent": user_agent,
                            "share_percentage": float(share) if share.replace('.', '').isdigit() else 0,
                            "device": device,
                            "browser_info": browser_info
                        })
            
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
                    # Handle different table structures
                    if len(cells) == 2:  # Windows/Mac/Linux format
                        browser_info = cells[0].get_text(strip=True)
                        ua_textarea = cells[1].find('textarea')
                        device = None
                    elif len(cells) == 3:  # Mobile format with device column
                        device = cells[0].get_text(strip=True)
                        browser_info = cells[1].get_text(strip=True)
                        ua_textarea = cells[2].find('textarea')
                    
                    if ua_textarea:
                        user_agent = ua_textarea.get_text(strip=True)
                        ua_data = {
                            "user_agent": user_agent,
                            "browser_info": browser_info
                        }
                        if device:
                            ua_data["device"] = device
                        user_agents.append(ua_data)
            
            return user_agents
        except Exception as e:
            print(f"Error extracting latest user agents for {section_id}: {e}")
            return []
    
    def save_json(self, data, filepath):
        """Save data to JSON file"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"Saved {len(data.get('user_agents', []))} user agents to {filepath}")
        except Exception as e:
            print(f"Error saving {filepath}: {e}")
    
    def run(self):
        """Main scraping function"""
        print("Starting user agent scraping...")
        
        # Scrape the main page
        soup = self.scrape_page()
        if not soup:
            print("Failed to scrape main page")
            return
        
        current_time = datetime.utcnow().isoformat() + "Z"
        
        # Extract and save common desktop user agents
        desktop_agents = self.extract_common_desktop(soup)
        if desktop_agents:
            desktop_data = {
                "scraped_at": current_time,
                "scraped_from": self.base_url,
                "type": "most_common_desktop",
                "count": len(desktop_agents),
                "user_agents": desktop_agents
            }
            self.save_json(desktop_data, "common/desktop.json")
        
        # Extract and save common mobile user agents
        mobile_agents = self.extract_common_mobile(soup)
        if mobile_agents:
            mobile_data = {
                "scraped_at": current_time,
                "scraped_from": self.base_url,
                "type": "most_common_mobile",
                "count": len(mobile_agents),
                "user_agents": mobile_agents
            }
            self.save_json(mobile_data, "common/mobile.json")
        
        # Extract latest user agents by category
        latest_sections = {
            "latest-windows-desktop-useragents": "latest/windows.json",
            "latest-mac-desktop-useragents": "latest/mac.json",
            "latest-linux-desktop-useragents": "latest/linux.json",
            "latest-iphone-useragents": "latest/iphone.json",
            "latest-ipod-useragents": "latest/ipod.json",
            "latest-ipad-useragents": "latest/ipad.json",
            "latest-android-mobile-useragents": "latest/android.json",
            "latest-tablet-useragents": "latest/tablet.json"
        }
        
        for section_id, filepath in latest_sections.items():
            agents = self.extract_latest_by_section(soup, section_id)
            if agents:
                # Extract type name from section_id
                type_name = section_id.replace("latest-", "").replace("-useragents", "").replace("-", "_")
                
                data = {
                    "scraped_at": current_time,
                    "scraped_from": self.base_url,
                    "type": f"latest_{type_name}",
                    "count": len(agents),
                    "user_agents": agents
                }
                self.save_json(data, filepath)
            
            # Small delay between requests
            time.sleep(0.1)
        
        print("Scraping completed successfully!")

if __name__ == "__main__":
    scraper = UserAgentScraper()
    scraper.run()