import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime
from tqdm import tqdm
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
import time


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

def _slugify(name: str) -> str:
    return name.lower().replace(" ", "-")

def collect_all_rankings(players_df, print_sample=True, sample_rows=8):
    # --- small, safe speed-ups ---
    options = Options()
    options.add_argument("--headless=new")                     # faster headless
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.set_capability("pageLoadStrategy", "none")         # we’ll wait for the bits we need

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(12)

    wait = WebDriverWait(driver, 10)

    # avoid per-iteration .loc cost
    name_to_id = players_df["Id"].to_dict()
    names = list(players_df.index)

    all_frames = []
    printed_sample = False

    try:
        for name in tqdm(names, desc="Collecting rankings", unit="player"):
            pid = name_to_id.get(name)
            if not pid:
                continue

            url = f"https://www.atptour.com/en/players/{_slugify(name)}/{pid}/rankings-history?year=all"

            rows_collected = False
            for attempt in (1, 2):  # tiny retry for flaky hydration
                try:
                    driver.get(url)

                    # Wait for nested cells, not just the row shell. This reduces "None/0" issues.
                    wait.until(EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "div.ranking-item dd.name span")
                    ))
                    wait.until(EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "div.ranking-item dd.points div.set-points div")
                    ))

                    # Small buffer to let text populate (keeps fast pages fast, helps slow ones)
                    time.sleep(0.15 if attempt == 1 else 0.35)

                    html = driver.page_source
                    soup = BeautifulSoup(html, "lxml")  # faster; falls back to html.parser if lxml unavailable
                    ranking_items = soup.select("div.ranking-item")

                    date_strs, rank_strs = [], []
                    for item in ranking_items:
                        type_ = item.select_one("dd.type")
                        if type_ and type_.get_text(strip=True) != "Singles":
                            continue

                        date = item.select_one("dd.name span")
                        rank = item.select_one("dd.points div.set-points div")

                        if not (date and rank):
                            continue

                        dtxt = date.get_text(strip=True)
                        rtxt = rank.get_text(strip=True)

                        if dtxt and rtxt:
                            date_strs.append(dtxt)
                            rank_strs.append(rtxt)

                    if date_strs and rank_strs:
                        # Vectorized conversions
                        dates = pd.to_datetime(pd.Series(date_strs), errors="coerce").dt.date
                        ranks = (
                            pd.Series(rank_strs)
                            .str.replace(",", "", regex=False)
                            .pipe(pd.to_numeric, errors="coerce")
                        )

                        df = (
                            pd.DataFrame({"Player": name, "Date": dates, "Rank": ranks})
                              .dropna(subset=["Date", "Rank"])
                              .drop_duplicates(subset="Date")
                        )

                        if not df.empty:
                            all_frames.append(df)

                            # Print a small sample once so you can sanity-check quickly
                            if print_sample and not printed_sample:
                                print("\nSample output (first player parsed):")
                                print(df.sort_values("Date", ascending=False).head(sample_rows).to_string(index=False))
                                printed_sample = True
                    break  # exit retry loop even if empty (we tried)

                except Exception as e:
                    if attempt == 2:
                        print(f"Error for player {name}: {e}")
                    # quick retry
                    continue

            # proceed to next player
            continue

    finally:
        driver.quit()

    return pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame(columns=["Player", "Date", "Rank"])

# def collect_all_rankings(players_df):
#     # --- Simple, safe speed-ups ---
#     options = Options()
#     options.add_argument("--headless=new")                     # faster headless
#     options.add_argument("--disable-gpu")
#     options.add_argument("--no-sandbox")
#     options.add_argument("--disable-dev-shm-usage")
#     options.add_argument("--blink-settings=imagesEnabled=false")  # skip images
#     options.set_capability("pageLoadStrategy", "none")         # don't wait for full load

#     driver = webdriver.Chrome(options=options)
#     wait = WebDriverWait(driver, 12)  # a bit tighter than 20s

#     all_frames = []

#     try:
#         for name in tqdm(players_df.index, desc="Collecting rankings", unit="player"):
#             try:
#                 url_name = name.lower().replace(" ", "-")
#                 player_id = players_df.loc[name, "Id"]
#                 url = f"https://www.atptour.com/en/players/{url_name}/{player_id}/rankings-history?year=all"

#                 driver.get(url)

#                 # Just wait until ranking items are present
#                 wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.ranking-item")))

#                 # Parse with BeautifulSoup (keeps your existing parsing logic)
#                 soup = BeautifulSoup(driver.page_source, "html.parser")
#                 ranking_items = soup.select("div.ranking-item")

#                 # Collect raw strings first (then vectorize conversion)
#                 date_strs, rank_strs = [], []
#                 for item in ranking_items:
#                     type_ = item.select_one("dd.type")
#                     if type_ and type_.get_text(strip=True) != "Singles":
#                         continue

#                     date = item.select_one("dd.name span")
#                     rank = item.select_one("dd.points div.set-points div")

#                     if date and rank:
#                         dtxt = date.get_text(strip=True)
#                         rtxt = rank.get_text(strip=True)
#                         if dtxt and rtxt:
#                             date_strs.append(dtxt)
#                             rank_strs.append(rtxt)

#                 if date_strs and rank_strs:
#                     # Vectorized conversions (faster & cleaner)
#                     dates = pd.to_datetime(pd.Series(date_strs), errors="coerce").dt.date
#                     ranks = pd.to_numeric(pd.Series(rank_strs).str.replace(",", ""), errors="coerce")

#                     df = pd.DataFrame({"Player": name, "Date": dates, "Rank": ranks})
#                     df = df.dropna(subset=["Date", "Rank"]).drop_duplicates(subset="Date")
#                     print(df)
#                     if not df.empty:
#                         all_frames.append(df)

#             except Exception as e:
#                 print(f"Error for player {name}: {e}")
#                 continue
#     finally:
#         driver.quit()

#     if all_frames:
#         return pd.concat(all_frames, ignore_index=True)
#     return pd.DataFrame(columns=["Player", "Date", "Rank"])

# async def add_surfaces(tournaments_df):
#     # Reuse ONE driver for the whole loops
#     options = Options()
#     options.add_argument("--headless=new")          # a bit faster/stabler headless
#     options.add_argument("--disable-gpu")
#     options.add_argument("--no-sandbox")
#     options.add_argument("--disable-dev-shm-usage")
#     options.add_argument("--blink-settings=imagesEnabled=false")  # don't load images
#     options.page_load_strategy = "eager"            # don't wait for all resources

#     driver = webdriver.Chrome(options=options)
#     wait = WebDriverWait(driver, 15)

#     surfaces = []
#     try:
#         # iterate exactly as before (your index appears to be (Name, Year))
#         for index in tqdm(tournaments_df.index.unique(), desc="Collecting tournament surfaces"):
#             name = index[0]
#             tid = int(tournaments_df.loc[index, 'Id'].iloc[0])  # same as before
        
#             url = "https://www.atptour.com/en/tournaments/%s/%d/overview" % (name, tid)
#             edge_cases = {'Adelaide 1' : 'Hard', 'Adelaide 2' : 'Hard', 'Adelaide' : 'Hard', 'Amersfoort' : 'Clay', 'Amsterdam' : 'Clay', 
#                         'Bunschoten' : 'Clay'}
#             if name in edge_cases:
#                 surfaces.append(edge_cases[name])
#             else:    
#                 surface = None
#                 try:
#                     driver.get(url)
#                     # Wait for the 'Surface' value span
#                     next_span_elem = wait.until(
#                         EC.presence_of_element_located(
#                             (By.XPATH, "//span[normalize-space()='Surface']/following-sibling::span[1]")
#                         )
#                     )
#                     content = next_span_elem.text.strip()
#                     if content in ('Hard', 'Clay', 'Grass'):
#                         surface = content
#                 except Exception as e:
#                     # keep your behavior: print and continue
#                     print(url)
#                     print(e)
#                     break
#                 finally:
#                     print(index, surface)
#                     surfaces.append(surface)

#     finally:
#         driver.quit()

#     tournaments_df = tournaments_df.copy()
#     tournaments_df['Surface'] = surfaces
#     return tournaments_df