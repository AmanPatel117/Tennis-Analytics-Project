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
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename='adding_players.log',
        filemode='w'
    )

    name, id_, year = index[0].lower(), tournaments_df.loc[index, 'Id'], index[1]
    url = f"https://www.atptour.com/en/scores/archive/{name}/{id_}/{int(year)}/results"

    try:
        page = requests.get(url, timeout=10).text
    except Exception as e:
        logging.error(f'Collecting match data for {(name, id_, year)} failed with error {str(e)}')
        return None

    soup = BeautifulSoup(page, "lxml")
    match_nodes = soup.select("div.match")

    p1_list, p2_list, winner_list, round_list = [], [], [], []

    for m in match_nodes:
        round_el = m.select_one("div.match-header strong")
        round_txt = (round_el.get_text(strip=True) if round_el else "").strip()
        if round_txt.endswith('-'):
            round_txt = round_txt[:-1].strip()
        round_txt = round_txt.split(' -', 1)[0].strip()

        player_links = m.select('a[href*="/players/"]')
        players = [a.get_text(strip=True) for a in player_links]
        if len(players) < 2:
            players = [a.get_text(strip=True) for a in m.select('a')]

        if len(players) < 2:
            continue

        if players[1].lower() == 'bye':
            continue

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

    df = df[df['Player 2'].str.lower() != 'bye'].reset_index(drop=True)

    return df


def add_players(index, tournaments_df):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename='adding_players.log',
        filemode='w'
    )
    name, id, year = index[0].lower(), tournaments_df.loc[index, 'Id'], index[1]
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

    names = [tag.text for tag in soup.find_all(custom_selector)]
    ids = [tag.get('value') for tag in soup.find_all(custom_selector)]
    return pd.DataFrame({'Name': names, 'Id': ids})


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

            date_location = soup1.find_all('div', class_='date-location')[1]
            text = date_location.get_text(strip=True)
            m1 = re.search(r'(\d{1,2} \w{3}) - (\d{1,2} \w{3}), (\d{4})', text)
            m2 = re.search(r'(\d{1,2})-(\d{1,2}) (\w{3}), (\d{4})', text)

            if m1:
                start_day, end_day, y = m1.group(1), m1.group(2), m1.group(3)
                start_date = f"{start_day}, {y}"
                end_date = f"{end_day}, {y}"
            elif m2:
                sd, ed, month, y = m2.group(1), m2.group(2), m2.group(3), m2.group(4)
                start_date = f"{sd} {month}, {y}"
                end_date = f"{ed} {month}, {y}"
            else:
                raise ValueError("Date format could not be parsed. Check website and add regex.")

            start_dates.append(datetime.strptime(start_date, "%d %b, %Y"))
            end_dates.append(datetime.strptime(end_date, "%d %b, %Y"))

            sel = soup1.select_one('select#matchRound-filter')
            if sel:
                options = [
                    o for o in sel.find_all('option')
                    if not re.match(r'^Q\d', o.get('value', '').upper())
                ]
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
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.set_capability("pageLoadStrategy", "none")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(12)
    wait = WebDriverWait(driver, 10)

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

            for attempt in (1, 2):
                try:
                    driver.get(url)
                    wait.until(EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "div.ranking-item dd.name span")
                    ))
                    wait.until(EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "div.ranking-item dd.points div.set-points div")
                    ))

                    time.sleep(0.15 if attempt == 1 else 0.35)

                    html = driver.page_source
                    soup = BeautifulSoup(html, "lxml")
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

                            if print_sample and not printed_sample:
                                print("\nSample output (first player parsed):")
                                print(df.sort_values("Date", ascending=False).tail(sample_rows).to_string(index=False))
                                printed_sample = True
                    break

                except Exception as e:
                    if attempt == 2:
                        print(f"Error for player {name}: {e}")
                    continue

            continue

    finally:
        driver.quit()

    return pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame(columns=["Player", "Date", "Rank"])