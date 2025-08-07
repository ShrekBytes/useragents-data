#!/usr/bin/env python3
"""
User Agent Scraper for useragents.me
Scrapes most common desktop and mobile user agents and saves to JSON files
"""

import requests
import json
import re
from bs4 import BeautifulSoup
from datetime import datetime
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def scrape_useragents():
    """
    Scrape user agents from useragents.me
    Returns dict with desktop and mobile user agents
    """
    url = "https://www.useragents.me"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
    }
    
    try:
        logger.info(f"Fetching data from {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract desktop user agents JSON
        desktop_json = extract_json_from_textarea(soup, 'most-common-desktop-useragents-json-csv')
        
        # Extract mobile user agents JSON  
        mobile_json = extract_json_from_textarea(soup, 'most-common-mobile-useragents-json-csv')
        
        if not desktop_json or not mobile_json:
            raise ValueError("Could not find user agent JSON data on the page")
        
        logger.info(f"Successfully extracted {len(desktop_json)} desktop and {len(mobile_json)} mobile user agents")
        
        return {
            'desktop': desktop_json,
            'mobile': mobile_json,
            'scraped_at': datetime.utcnow().isoformat() + 'Z',
            'source': url
        }
        
    except requests.RequestException as e:
        logger.error(f"Error fetching data from {url}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error parsing data: {e}")
        raise

def extract_json_from_textarea(soup, section_id):
    """
    Extract JSON data from textarea within a specific section
    """
    try:
        # Find the section div
        section_div = soup.find('div', {'id': section_id})
        if not section_div:
            logger.warning(f"Could not find section with id: {section_id}")
            return None
        
        # Find the JSON column (first col-lg-6 div)
        json_col = section_div.find('div', class_='col-lg-6')
        if not json_col:
            logger.warning(f"Could not find JSON column in section: {section_id}")
            return None
        
        # Find textarea with JSON content
        textarea = json_col.find('textarea')
        if not textarea:
            logger.warning(f"Could not find textarea in section: {section_id}")
            return None
        
        json_text = textarea.get_text().strip()
        if not json_text:
            logger.warning(f"Empty JSON content in section: {section_id}")
            return None
        
        # Parse JSON
        json_data = json.loads(json_text)
        return json_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON in section {section_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error extracting JSON from section {section_id}: {e}")
        return None

def save_json_file(data, filename):
    """
    Save data to JSON file with proper formatting
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Successfully saved data to {filename}")
    except Exception as e:
        logger.error(f"Error saving to {filename}: {e}")
        raise

def main():
    """
    Main function to scrape and save user agents
    """
    try:
        logger.info("Starting user agent scraping...")
        
        # Add delay to be respectful to the server
        time.sleep(2)
        
        # Scrape user agents
        data = scrape_useragents()
        
        # Prepare desktop data with metadata
        desktop_data = {
            'scraped_at': data['scraped_at'],
            'source': data['source'],
            'user_agents': data['desktop']
        }
        
        # Prepare mobile data with metadata
        mobile_data = {
            'scraped_at': data['scraped_at'],
            'source': data['source'],
            'user_agents': data['mobile']
        }
        
        # Save to separate files
        save_json_file(desktop_data, 'common-desktop.json')
        save_json_file(mobile_data, 'common-mobile.json')
        
        logger.info("User agent scraping completed successfully!")
        
        # Print summary
        print(f"✅ Desktop user agents: {len(data['desktop'])}")
        print(f"✅ Mobile user agents: {len(data['mobile'])}")
        print(f"✅ Scraped at: {data['scraped_at']}")
        
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        print(f"❌ Scraping failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()