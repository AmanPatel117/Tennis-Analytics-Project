import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import numpy as np
from datetime import datetime
import random
import os
import sys
import pickle
import xgboost as xgb
from sklearn.preprocessing import StandardScaler

def convert_name(name):
    lname = name.split(' ')[-1]
    first_initial = name[0]
    return '%s %s.' %(lname, first_initial)

def make_swaps(features_set): 
    p1, p2, p1_rank, p2_rank = list(features_set['Player 1']), list(features_set['Player 2']), list(features_set['Player 1 Ranking']), list(features_set['Player 2 Ranking'])
    p1_prev, p2_prev = list(features_set['Player 1 Previous Wins']), list(features_set['Player 2 Previous Wins'])
    p1_surface, p2_surface = list(features_set['P1 Surface Matches']), list(features_set['P2 Surface Matches'])
    p1_surf_wins, p2_surf_wins = list(features_set['P1 Surface Wins']), list(features_set['P2 Surface Wins'])
    p1_10, p2_10 = list(features_set['P1 Last 10 Matches']), list(features_set['P2 Last 10 Matches'])

    for i in range(len(p1)):
        if random.random() > 0.5:
            temp = p1[i]
            p1[i] = p2[i]
            p2[i] = temp

            temp = p1_rank[i]
            p1_rank[i] = p2_rank[i]
            p2_rank[i] = temp
            
            temp = p1_prev[i]
            p1_prev[i] = p2_prev[i]
            p2_prev[i] = temp

            temp = p1_surface[i]
            p1_surface[i] = p2_surface[i]
            p2_surface[i] = temp

            temp = p1_surf_wins[i]
            p1_surf_wins[i] = p2_surf_wins[i]
            p2_surf_wins[i] = temp

            temp = p1_10[i]
            p1_10[i] = p2_10[i]
            p2_10[i] = temp        
            
    features_set = pd.DataFrame({'P1' : p1, 'P2' : p2, 'Winner' : features_set['Winner'], 'P1 Ranking' : p1_rank, 'P2 Ranking' : p2_rank})
    features_set['P1 Previous Wins'], features_set['P2 Previous Wins'], features_set['P1 Surface Matches'], features_set['P2 Surface Matches'] = p1_prev, p2_prev, p1_surface, p2_surface
    features_set['P1 Surface Wins'], features_set['P2 Surface Wins'], features_set['P1 Last 10 Matches'], features_set['P2 Last 10 Matches'] = p1_surf_wins, p2_surf_wins, p1_10, p2_10
    features_set['winner'] = features_set.apply(lambda x: 0 if x['Winner'] == x['P1'] else 1, axis = 1)
    features_set = features_set.drop(['P1' ,'P2', 'Winner'], axis = 1)
    return features_set


def simulate(w, l):
    df = pd.read_csv('../Data/df_atp.csv')
    df.drop(df.columns[0], axis = 1, inplace =True)
    df = df.dropna(subset=[w, l])
    df = df[['Winner', 'Loser', 'Location', 'Date', w, l]]
    df = df.rename({'Location' : 'Tournament Name', 'Date' : 'Year'}, axis = 1)
    df['Year'] = df['Year'].astype('datetime64')
    df['Year'] = df['Year'].dt.year

    matches_df = pd.read_csv('../Data/matches.csv')
    matches_df = matches_df.drop(matches_df.columns[[0, 1]], axis = 1)
    matches_df = matches_df.rename({'Player 2' : 'Loser'}, axis = 1)
    matches_df['Loser'] = matches_df['Loser'].apply(convert_name)
    matches_df['Winner'] = matches_df['Winner'].apply(convert_name)
    locations_list = [location.title() for location in list(df['Tournament Name'].unique())]
    matches = matches_df[matches_df['Tournament Name'].isin(locations_list)]
    gambling_set = matches.merge(df, on = ['Loser', 'Winner', 'Tournament Name', 'Year'])
    gambling_set['winner'] = gambling_set['Winner']
    gambling_set = gambling_set.rename({'Loser' : 'Player 1', 'Winner' : 'Player 2', 'winner' : 'Winner'}, axis = 1)
    features_set = gambling_set

    on = list(matches_df.columns[2:])
    anti_join_result = pd.merge(matches_df, features_set, on=on, how='left', indicator=True).query("_merge == 'left_only'")
    anti_join_result = anti_join_result.drop(['Tournament Name', 'Year', 'Score', '_merge', w, l, 'Date', 'Player 1', 'Player 2', 'Winner_y'], axis = 1)
    anti_join_result['Winner'] = anti_join_result['Winner_x']
    X_train = anti_join_result.rename({'Loser' : 'Player 1', 'Winner_x' : 'Player 2'}, axis = 1)

    features_set = make_swaps(features_set)
    X_train = make_swaps(X_train)


    X_train, y_train = X_train.drop('winner', axis = 1).values, X_train['winner']
    y_test = features_set['winner']
    X_test = features_set.drop('winner', axis = 1).values
    scaler = StandardScaler()
    scaler.fit(X_train)
    X_train, X_test = scaler.transform(X_train), scaler.transform(X_test)

    model = xgb.XGBClassifier(booster = 'dart', n_estimators = 30, max_depth = 10)
    model.fit(X_train, y_train)
    model.score(X_test, y_test)

    gambling_features = make_swaps(gambling_set)
    gambling_test = gambling_features['winner']
    gambling_features = gambling_features.drop('winner', axis = 1)

    initial_amt, betting_amt = 1000, 50
    num_correct = 0
    for index, row in gambling_features.iterrows():
        row = np.array([row])
        row = scaler.transform(row)
        pred = model.predict(row)
        if pred[0] == gambling_test[index]:
            num_correct += 1
            odds = gambling_set.loc[index, w]
            initial_amt += betting_amt * (float(odds) - 1)
        else:
            initial_amt -= betting_amt
    profit = initial_amt - 1000
    return profit
  

