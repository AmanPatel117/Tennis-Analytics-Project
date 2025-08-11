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
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup


def collect_tourney_data(index, tournaments_df) -> pd.DataFrame:
    # (You probably want to configure logging once at program start, not per-call.)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename='adding_players.log',
        filemode='w'
    )

    name, id_, year = index[0].lower(), tournaments_df.loc[index, 'Id'].iloc[0], index[1]
    url = f"https://www.atptour.com/en/scores/archive/{name}/{id_}/{int(year)}/results"
    print(url)

    try:
        page = requests.get(url, timeout=10).text
    except Exception as e:
        logging.error(f'Collecting match data for {(name, id_, year)} failed with error {str(e)}')
        return None

    soup = BeautifulSoup(page, "lxml")

    # Each match is contained in a div.match which has a header (round) and content (players)
    match_nodes = soup.select("div.match")

    p1_list, p2_list, winner_list, round_list = [], [], [], []

    for m in match_nodes:
        # Round text: <div class="match-header"><span><strong>Finals - </strong></span> ...
        round_el = m.select_one("div.match-header strong")
        round_txt = (round_el.get_text(strip=True) if round_el else "").strip()
        # Clean "Finals -", "Quarterfinals -" etc -> remove trailing "- ..."
        if round_txt.endswith('-'):
            round_txt = round_txt[:-1].strip()
        # Some pages encode rounds like "R32 -", keep as-is but strip the dash
        round_txt = round_txt.split(' -', 1)[0].strip()

        # Players: two <a> links inside this match block that point to /players/
        # (more robust than a generic <a>)
        player_links = m.select('a[href*="/players/"]')
        players = [a.get_text(strip=True) for a in player_links]
        if len(players) < 2:
            # Fallback: try any <a> if player links weren't matched
            players = [a.get_text(strip=True) for a in m.select('a')]

        if len(players) < 2:
            continue  # skip malformed blocks

        # Some rows include “Bye”
        if players[1].lower() == 'bye':
            continue

        # On the results archive, the first listed name is the winner.
        p1_list.append(players[0])
        p2_list.append(players[1])
        winner_list.append(players[0])
        round_list.append(round_txt if round_txt else None)

    if not p1_list:
        return None

    df = pd.DataFrame({
        'Player 1': p1_list,
        'Player 2': p2_list,
        'Winner': winner_list,
        'Round': round_list
    })

    df['Tournament Name'] = name.title()
    df['Year'] = int(year)

    # Final tidy
    df = df[df['Player 2'].str.lower() != 'bye'].reset_index(drop=True)

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
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename='app.log',
        filemode='w'
    )

    tournaments_page = f'https://www.atptour.com/en/scores/results-archive?year={int(year)}'
    tags, names, numbers, start_dates, end_dates, num_rounds = [], [], [], [], [], []

    page = requests.get(tournaments_page, timeout=15).text
    soup = BeautifulSoup(page, features="lxml")

    # Options in the tournaments selector carry the tournament id
    def tournament_option(tag):
        return tag.name == 'option' and tag.has_attr("value") and tag.has_attr('class')

    for tag in soup.find_all(tournament_option):
        tags.append(tag)

    for tag in tags:
        url_number = int(tag.get('value'))
        t = str(tag)
        t = t[t.find('>') + 1:]
        name = t[:t.find('<')].strip().title()
        names.append(name)
        numbers.append(url_number)

    for i in range(len(names)):
        name, num = names[i], numbers[i]
        name_slug = name.replace(" ", "-")
        url = f'https://www.atptour.com/en/scores/archive/{name_slug}/{num}/{int(year)}/results'

        try:
            page = requests.get(url, timeout=15).text
            soup1 = BeautifulSoup(page, features="lxml")

            # --- Dates ---
            date_location = soup1.find_all('div', class_='date-location')[1]
            text = date_location.get_text(strip=True)
            m1 = re.search(r'(\d{1,2} \w{3}) - (\d{1,2} \w{3}), (\d{4})', text)
            m2 = re.search(r'(\d{1,2})-(\d{1,2}) (\w{3}), (\d{4})', text)

            if m1:
                start_day, end_day, y = m1.group(1), m1.group(2), m1.group(3)
                start_date = f"{start_day}, {y}"
                end_date   = f"{end_day}, {y}"
            elif m2:
                sd, ed, month, y = m2.group(1), m2.group(2), m2.group(3), m2.group(4)
                start_date = f"{sd} {month}, {y}"
                end_date   = f"{ed} {month}, {y}"
            else:
                raise ValueError("Date format could not be parsed. Check website and add regex.")

            start_dates.append(datetime.strptime(start_date, "%d %b, %Y"))
            end_dates.append(datetime.strptime(end_date, "%d %b, %Y"))

            # --- Number of Rounds (main draw only) ---
            sel = soup1.select_one('select#matchRound-filter')
            if sel:
                options = [
                    o for o in sel.find_all('option')
                    if not re.match(r'^Q\d', o.get('value', '').upper())  # exclude Q1, Q2, etc., but keep QF
                ]
                # Subtract 1 for "Round (All)" option
                count = max(len(options) - 1, 0)
            else:
                count = None

            num_rounds.append(count)

        except Exception as e:
            logging.error(f'Scraping failed for {(name, num, year)} with error {str(e)}')
            start_dates.append(pd.NaT)
            end_dates.append(pd.NaT)
            num_rounds.append(None)

    tournaments = pd.DataFrame({
        'Name': names,
        'Id': numbers,
        'Start Date': start_dates,
        'End Date': end_dates,
        'Number of Rounds': num_rounds,
    })
    return tournaments

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

# # OLD FUNCTIONS
# async def collect_rankings(name, players_df):
#     try:
#         url_name, player_id = name.lower().replace(" ", '-'), players_df.loc[name, 'Id']
#     except Exception as e:
#         print(e)
#         return -1
#     ranking_page_url = 'https://www.atptour.com/en/players/%s/%s/rankings-history?year=all' % (url_name, player_id)

#     # Setup Chrome in headless mode
#     options = Options()
#     options.add_argument("--headless")
#     driver = webdriver.Chrome(options=options)

#     try:
#         driver.get(ranking_page_url)
#         # Wait for the rankings table items to load
#         WebDriverWait(driver, 20).until(
#             EC.presence_of_element_located((By.CSS_SELECTOR, "div.ranking-item"))
#         )
#         # Get page source after JS execution
#         html = driver.page_source

#         # Parse with BeautifulSoup
#         soup = BeautifulSoup(html, "html.parser")
#         ranking_items = soup.select("div.ranking-item")

#         ranks, dates = [], []

#         for item in ranking_items:
#             type_ = item.select_one("dd.type")
#             if type_ and type_.get_text(strip=True) != "Singles":
#                 continue  # Skip doubles

#             date = item.select_one("dd.name span")
#             rank = item.select_one("dd.points div.set-points div")

#             date_text = date.get_text(strip=True) if date else "N/A"
#             rank_text = rank.get_text(strip=True) if rank else "N/A"

#             dates.append(pd.to_datetime(date_text).date())
#             ranks.append(int(rank_text))

#         df = pd.DataFrame()
#         df['Player'] = [name] * (len(dates))
#         df['Date'] = dates
#         df['Rank'] = ranks
#     except Exception as e:
#         print("Error:", e)
#         return None
#     finally:
#         driver.quit()
#     return df.drop_duplicates(subset='Date')