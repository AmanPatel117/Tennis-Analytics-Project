import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime
from tqdm.asyncio import tqdm_asyncio
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


def collect_tourney_data(index, tournaments_df) -> pd.DataFrame:
    logging.basicConfig(
    level=logging.INFO,                          # Minimum log level
    format='%(asctime)s - %(levelname)s - %(message)s',  # Log format
    filename='adding_players.log',                          # Optional: log to a file
    filemode='w'                                 # Optional: 'w' to overwrite, 'a' to append
    )
    name, id, year = index[0].lower(), tournaments_df.loc[index, 'Id'].iloc[0], index[1]
    url = "https://www.atptour.com/en/scores/archive/%s/%s/%d/results" % (name, id, year)
    print(url)
    try:
        page = requests.get(url, timeout = 10).text
    except Exception as e:
        logging.error(f'Collecting match data for {(name, id, year)} failed with error {str(e)}')
        return None
    soup = BeautifulSoup(page, features="lxml")

    def match_selector(tag):
        return tag.name == 'div' and tag.has_attr('class') and 'match-stats' in tag['class']
    
    def player_selector(tag):
        return tag.name == 'a' and tag.has_attr('href')
    
    match_tags = soup.find_all(match_selector)

    player1, player2, winners = [], [], []
    for match_tag in match_tags:
        players = [player_tag.text for player_tag in match_tag.find_all(player_selector)]
        if players == []:
            continue
        player1.append(players[0])
        player2.append(players[1])
        winners.append(players[0])
        
    df = pd.DataFrame({'Player 1' : player1, 'Player 2' : player2, 'Winner' : winners})
    df['Tournament Name'] = name.title()
    df = df[df['Player 2'] != 'Bye']
    df['Year'] = year
    return df

def add_players(index, tournaments_df):
    logging.basicConfig(
    level=logging.INFO,                          # Minimum log level
    format='%(asctime)s - %(levelname)s - %(message)s',  # Log format
    filename='adding_players.log',                          # Optional: log to a file
    filemode='w'                                 # Optional: 'w' to overwrite, 'a' to append
    )
    name, id, year = index[0].lower(), tournaments_df.loc[index, 'Id'].iloc[0], index[1]
    url = "https://www.atptour.com/en/scores/archive/%s/%s/%s/results" % (name, id, year)
    try:
        page = requests.get(url, timeout=10).text
    except Exception as e:
        logging.error(f'Adding players failed for {(name, id, year)} with error {str(e)}')
        return None
    page = page[page.find('<option selected="selected" value="">Player (All)</option>'):]
    page = page[:page.find('</select>')]

    soup = BeautifulSoup(page, features="lxml")

    def custom_selector(tag):
        return tag.name == 'option' and tag.has_attr('value') and not tag.has_attr('selected') 
    #Gets rid of country tags
    names = [tag.text for tag in soup.find_all(custom_selector)]
    ids = [tag.get('value') for tag in soup.find_all(custom_selector)]
    return pd.DataFrame({'Name' : names, 'Id' : ids})

def collect_tournaments(year):
    logging.basicConfig(
    level=logging.INFO,                          # Minimum log level
    format='%(asctime)s - %(levelname)s - %(message)s',  # Log format
    filename='app.log',                          # Optional: log to a file
    filemode='w'                                 # Optional: 'w' to overwrite, 'a' to append
    )

    tournaments_page = 'https://www.atptour.com/en/scores/results-archive?year=%d' % (year)
    tags, names, numbers, start_dates, end_dates = [], [], [], [], []
    page = requests.get(tournaments_page).text

    start = page.find('<select id="tournament"')
    tournament_string = page[start:]
    end = tournament_string.find('</select>')

    tournament_string = tournament_string[:end]
    soup = BeautifulSoup(page, features="lxml")

    def custom_selector(tag):
        if tag.name == 'option' and tag.has_attr("value") and tag.has_attr('class'):
            return True
        return False
    for tag in soup.find_all(custom_selector):
        tags.append(tag)
    for tag in tags:
        url_number = int(tag.get('value'))
        tag = str(tag)
        tag = tag[tag.find('>') + 1:]
        name = tag[:tag.find('<')].strip().title()
        names.append(name)
        numbers.append(url_number)

    for i in range(len(names)):
        name, num = names[i], numbers[i]
        name = name.replace(" ", "-")
        url = 'https://www.atptour.com/en/scores/archive/%s/%s/%s/results' % (name, num, year)
        try:
            page = requests.get(url, timeout = 10).text
            soup1 = BeautifulSoup(page, features="html.parser")
            date_location = soup1.find_all('div', class_='date-location')[1]
        except Exception as e:
            logging.error(f'Scraping failed for {(name, num, year)} with error {str(e)}')

        text = date_location.get_text(strip=True)
        # Regex to match patterns like: 27 Feb - 4 Mar, 2023
        match = re.search(r'(\d{1,2} \w{3}) - (\d{1,2} \w{3}), (\d{4})', text)

        match2 = re.search(r'(\d{1,2})-(\d{1,2}) (\w{3}), (\d{4})', text)
        
        if match:
            start_day = match.group(1)
            end_day = match.group(2)
            year = match.group(3)
            start_date = f"{start_day}, {year}"
            end_date = f"{end_day}, {year}"
        elif match2:
            start_day = match2.group(1)
            end_day = match2.group(2)
            month = match2.group(3)
            year = match2.group(4)
            start_date = f"{start_day} {month}, {year}"
            end_date = f"{end_day} {month}, {year}"
        else:
            raise Exception("Date format could not be parsed. Check website and add regex.")
        start_dates.append(datetime.strptime(start_date, "%d %b, %Y"))
        end_dates.append(datetime.strptime(end_date, "%d %b, %Y"))
    tournaments = pd.DataFrame({'Name' : names, 'Id' : numbers, 'Start Date' : start_dates, 'End Date' : end_dates})
    return tournaments

async def collect_rankings(name, players_df):
    try:
        url_name, player_id = name.lower().replace(" ", '-'), players_df.loc[name, 'Id']
    except Exception as e:
        print(e)
        return -1
    ranking_page_url = 'https://www.atptour.com/en/players/%s/%s/rankings-history?year=all' % (url_name, player_id)

    # Setup Chrome in headless mode
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(ranking_page_url)
        # Wait for the rankings table items to load
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.ranking-item"))
        )
        # Get page source after JS execution
        html = driver.page_source

        # Parse with BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        ranking_items = soup.select("div.ranking-item")

        ranks, dates = [], []

        for item in ranking_items:
            type_ = item.select_one("dd.type")
            if type_ and type_.get_text(strip=True) != "Singles":
                continue  # Skip doubles

            date = item.select_one("dd.name span")
            rank = item.select_one("dd.points div.set-points div")

            date_text = date.get_text(strip=True) if date else "N/A"
            rank_text = rank.get_text(strip=True) if rank else "N/A"

            dates.append(pd.to_datetime(date_text).date())
            ranks.append(int(rank_text))

        df = pd.DataFrame()
        df['Player'] = [name] * (len(dates))
        df['Date'] = dates
        df['Rank'] = ranks
    except Exception as e:
        print("Error:", e)
        return None
    finally:
        driver.quit()
    return df.drop_duplicates(subset='Date')

async def add_surfaces(tournaments_df):
    surfaces = []
    for index in tqdm_asyncio(tournaments_df.index.unique(), desc="Collecting player rankings"):
        name, id = index[0], tournaments_df.loc[index, 'Id'].iloc[0]
        url = 'https://www.atptour.com/en/tournaments/%s/%d/overview' % (name, id)
        options = Options()
        options.add_argument("--headless")
        driver = webdriver.Chrome(options=options)
        surface = None
        try:
            driver.get(url)
            # Wait for both 'Surface' span and its next sibling to exist
            next_span_elem = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//span[normalize-space()='Surface']/following-sibling::span[1]")
                )
            )
            # Get the text of that next span
            content = next_span_elem.text
            if content in ['Hard', 'Clay', 'Grass']:
                surface = content
            surfaces.append(surface)
        except Exception as e:
            print(e)
        finally:
            driver.quit()
    tournaments_df['Surface'] = surfaces
    return tournaments_df





















# pip install playwright tqdm pandas
# python -m playwright install chromium

import asyncio
from playwright.async_api import async_playwright
import pandas as pd
from tqdm.asyncio import tqdm_asyncio

ATP_TMPL = "https://www.atptour.com/en/players/{slug}/{pid}/rankings-history?year=all"

def slugify(name: str) -> str:
    return name.lower().replace(" ", "-")

async def _fetch_player_rankings(name: str, pid: str, context, timeout_ms=20000):
    """Open one page, extract Singles ranking rows, return list[dict]."""
    url = ATP_TMPL.format(slug=slugify(name), pid=pid)
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # Wait for the ranking items to exist (page is dynamic)
        await page.wait_for_selector("div.ranking-item", timeout=timeout_ms)

        # Extract on the page (JS side) to avoid HTML round‑trips
        rows = await page.eval_on_selector_all(
            "div.ranking-item",
            """els => els.map(el => {
                const type = el.querySelector('dd.type')?.textContent?.trim();
                if (type && type !== 'Singles') return null;
                const d = el.querySelector('dd.name span')?.textContent?.trim();
                const r = el.querySelector('dd.points div.set-points div')?.textContent?.trim();
                if (!d || !r) return null;
                const rank = parseInt(String(r).replace(/[^0-9]/g, ''), 10);
                if (Number.isNaN(rank)) return null;
                return {date: d, rank};
            }).filter(Boolean)"""
        )
        # Build pandas-friendly records
        recs = [{"Player": name, "Date": pd.to_datetime(r["date"]).date(), "Rank": r["rank"]} for r in rows]
        return recs
    except Exception as e:
        # return empty list to keep the pipeline moving
        # you can log `e` if you want
        return []
    finally:
        await page.close()

async def collect_all_rankings(players_df: pd.DataFrame, max_concurrency: int = 8):
    """
    players_df: index is player name; must have column 'Id'
    Returns a DataFrame with columns: Player, Date, Rank
    """
    names = players_df.index.unique().tolist()
    ids = players_df.loc[names, "Id"].astype(str).tolist()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        sem = asyncio.Semaphore(max_concurrency)

        async def runner(name, pid):
            async with sem:
                return await _fetch_player_rankings(name, pid, context)

        tasks = [runner(n, i) for n, i in zip(names, ids)]
        # tqdm on asyncio
        results_nested = await tqdm_asyncio.gather(*tasks, desc="Collecting rankings", total=len(tasks))

        await context.close()
        await browser.close()

    # Flatten and build one DataFrame once (fast)
    flat = [row for recs in results_nested for row in recs]
    if not flat:
        return pd.DataFrame(columns=["Player", "Date", "Rank"])
    out = pd.DataFrame(flat).drop_duplicates(subset=["Player", "Date"]).sort_values(["Player", "Date"])
    return out

