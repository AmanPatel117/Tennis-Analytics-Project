import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import numpy as np
from datetime import datetime
import random
import logging

def collect_matches(soup):
    player1, player2, winner = [], [], []
    index = 0
    for tag in soup.find_all('td', {'class' : 'day-table-name'}):
        tag = str(tag)
        if '<a' in tag:
            tag = tag[tag.find('>') + 1:]
            tag = tag[tag.find('>') + 1:]
            name = tag[:tag.find('<')]
        else:
            tag = tag[tag.find('>') + 1:]
            name = tag[:tag.find('<')].strip()
        if index % 2 == 0:
            player1.append(name)
            winner.append(name)
        else:
            player2.append(name)
        index += 1
    return player1, player2, winner

def collect_scores(soup):
    scores = []
    for tag in soup.find_all('td', {'class' : 'day-table-score'}):
        tag = str(tag)
        score = ''
        while '-->' in tag:
            tag = tag[tag.find('-->') + 5:]
            score += tag[:2]
        scores.append(score)
    return scores

def collect_tourney_data(index, tournaments_df) -> pd.DataFrame:
    name, id, year = index[0].lower(), tournaments_df.loc[index, 'Id'][0], index[1]
    url = "https://www.atptour.com/en/scores/archive/%s/%s/%d/results" % (name, id, year)
    page = requests.get(url).text
    soup = BeautifulSoup(page, features="lxml")
    player1, player2, winner= collect_matches(soup)
    scores = collect_scores(soup)
    df = pd.DataFrame({'Player 1' : player1, 'Player 2' : player2, 'Winner' : winner, 'Score' : scores})
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
    name, id, year = index[0].lower(), tournaments_df.loc[index, 'Id'][0], index[1]
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
        if tag.name == 'option' and tag.has_attr('value') and not tag.has_attr('selected'):
            return True
        return False
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
        print(name, num, year)
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

def find_ranking(row, tournaments_df, players_df, player1 = True):
    name = row['Player 1'] if player1 else row['Player 2']
    tournament, year = row['Tournament Name'], row['Year']
    tournament_id = tournaments_df.loc[(tournament, year), 'Id'][0]
    try:
        url = 'https://www.atptour.com/en/scores/archive/%s/%d/%d/results' % (tournament.lower(), tournament_id, year)
        page = requests.get(url).text
    except Exception as e:
        return -1
    soup = BeautifulSoup(page, features="lxml")

    start_date = tournaments_df.loc[(tournament, year), 'Start Date'][0]
    try:
        name, player_id = name.lower().replace(" ", '-'), players_df.loc[name, 'Id']
    except Exception as e:
        print(e)
        return -1
    ranking_page = 'https://www.atptour.com/en/players/%s/%s/rankings-history' % (name, player_id)
    historical_ranking = requests.get(ranking_page).text
    soup1 = BeautifulSoup(historical_ranking, features="lxml")

    dates, contents, format = [], [], '%Y.%m.%d'
    date_to_ranking = {}
    for tag in soup1.find_all('td'):
        tag = str(tag)[4:]
        content = tag[:tag.find('<')].strip()
        contents.append(content)
    for index, content in enumerate(contents):
        try:
            date = datetime.strptime(content, format)
            dates.append(date)
            ranking = int(contents[index + 1])
            date_to_ranking[content] = ranking
        except:
            continue

    ranking_date = -1
    start_date = datetime.strptime(start_date, '%Y-%m-%d')
    for index, date in enumerate(dates):
        if date <= start_date:
            ranking_date = date
            break
    try:
        ranking = date_to_ranking[datetime.strftime(ranking_date, format)]
    except:
        return -1
    return ranking