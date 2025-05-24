import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import numpy as np
from datetime import datetime
import random

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
    name, id, year = index[0].lower(), tournaments_df.loc[index, 'Id'][0], index[1]
    url = "https://www.atptour.com/en/scores/archive/%s/%s/%d/results" % (name, id, year)
    page = requests.get(url).text
    soup = BeautifulSoup(page, features="lxml")
    def custom_selector(tag):
        if tag.name == 'li' and tag.has_attr('data-value'):
            return True
        return False
    #Gets rid of country tags
    tags = [tag for tag in soup.find_all(custom_selector) if bool(re.search(r'\d', tag.get('data-value')))]
    #Removing tags that are not names
    names, ids = [], []
    for tag in enumerate(reversed(tags)):
        tag = str(tag[1])
        ue = tag.find('ue')
        id = tag[ue + 4: ue + 8]
        tag = tag[tag.find('>')+1:]
        name = tag[:tag.find('<')]
        if 'Round' in tag:
            break
        else:
            names.append(name)
            ids.append(id)
    return pd.DataFrame({'Name' : names, 'Id' : ids})

def collect_tournaments(year):    
    tournaments_page = 'https://www.atptour.com/en/scores/results-archive?year=%d' % (year)
    tags, names, numbers, start_date, end_date, surfaces = [], [], [], [], [], []
    page = requests.get(tournaments_page).text
    soup = BeautifulSoup(page, features="lxml")
    def custom_selector(tag):
        if tag.name == 'li' and tag.has_attr("data-value") and tag.has_attr('class'):
            return True
        return False
    for tag in soup.find_all(custom_selector):
        tags.append(tag)
    tags = tags[110:-7]
    for tag in tags:
        url_number = int(tag.get('data-value'))
        tag = str(tag)
        tag = tag[tag.find('>') + 1:]
        name = tag[:tag.find('<')].strip().title()
        names.append(name)
        print(name)
        numbers.append(url_number)
    for i in range(len(names)):
        name, num = names[i], numbers[i]
        print(name, num)
        url = 'https://www.atptour.com/en/scores/archive/%s/%d/%d/results' % (name, num, year)
        page = requests.get(url).text
        soup1 = BeautifulSoup(page, features="html.parser")
        for tag in soup1.find_all('span', {'class' : 'tourney-dates'}):
            tag = str(tag)
            tag = tag[tag.find('>')+1:]
            tag = tag[:tag.find('<')].strip()
            dates = [date.strip() for date in tag.split('-')]
        start_date.append(datetime.strptime(dates[0], '%Y.%m.%d'))
        end_date.append(datetime.strptime(dates[1], '%Y.%m.%d'))
    tournaments = pd.DataFrame({'Name' : names, 'Id' : numbers, 'Start Date' : start_date, 'End Date' : end_date, 'Surface' : surfaces})
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