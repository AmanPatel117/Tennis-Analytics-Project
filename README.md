# 🎾 Tennis Sports Betting Model

This project builds and evaluates a sports betting model for ATP tennis matches using scraped data from the official ATP Tour website. It leverages historical match results, player rankings, and odds data to simulate a betting strategy and estimate potential profitability.

---

## 📁 Project Structure

- `scraping_functions.py`: Web scraping utilities to collect ATP match results, tournament data, and player rankings.
- `gambling_simulation.py`: Constructs a predictive model and simulates a betting strategy using match features and historical odds.

---

## 🧠 Model Overview

- **Data Sources**:
  - Match results and scores
  - Player names and rankings
  - Tournament metadata (location, surface, year)
- **Feature Engineering**:
  - Positional bias reduction via random swaps
  - Historical performance features (surface wins, ranking, previous wins, recent form)
- **Model**:
  - `XGBoost` classifier (`booster='dart'`, `n_estimators=30`, `max_depth=10`)
  - Input: Engineered match features
  - Output: Winner prediction
- **Simulation**:
  - Simulates $50 bets on model predictions
  - Real odds used to calculate payout
  - Profit computed against a $1000 initial bankroll

---

## 🔍 Simulation Function

```python
simulate(w: str, l: str) -> float
```

- `w`: Column name for winner odds  
- `l`: Column name for loser odds  
- **Returns**: Simulated profit in USD

---

## 🛠 Requirements

- Python libraries:
  - `pandas`
  - `numpy`
  - `requests`
  - `beautifulsoup4`
  - `scikit-learn`
  - `xgboost`

Install with:

```bash
pip install pandas numpy requests beautifulsoup4 scikit-learn xgboost
```

---

## 💡 Usage

1. **Scrape Tournament and Match Data**

   Use functions in `scraping_functions.py` to gather tournament results and player information.

2. **Build Feature Set**

   Enrich data with rankings and match-level statistics.

3. **Run Simulation**

   Call the `simulate()` function from `gambling_simulation.py`:

   ```python
   from gambling_simulation import simulate
   profit = simulate('Winner Odds', 'Loser Odds')
   print(f"Profit: ${profit}")
   ```

---

## 📈 Example Output

```
Initial bankroll: $1000  
Bets placed: 100  
Correct predictions: 64%  
Final bankroll: $1180  
Profit: $180
```

---

## ⚠️ Disclaimer

This project is for educational and research purposes only. It does **not** constitute financial or betting advice. Use at your own risk.
