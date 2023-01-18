import requests
import pandas as pd
import math
import os
from scipy.stats import norm

pd.set_option('display.max_rows', None)

# GLOBALS
API_KEY = "OeAFFmMliFG5orCUuwAKQ8l4WWFQ67YX"

MEMORY = {}

OPTIONS = {}

RENAME_MAP = {
    'CALL': {
        'strike': 'Strike', 
        'contractName': 'cName',
        'lastPrice': 'lastPrice', 
        'bid': 'cBidP', 
        'ask': 'cAskP',
        'volume': 'cVolume', 
        'impliedVolatility': 'impliedVolatility', 
        'delta': 'cDelta', 
        'gamma': 'Gamma', 
        'theta': 'Theta', 
        'vega': 'Vega', 
        'rho': 'Rho'
    },
    'PUT': {
        'strike': 'Strike', 
        'contractName': 'pName',
        'lastPrice': 'lastPrice', 
        'bid': 'pBidP', 
        'ask': 'pAskP',
        'volume': 'pVolume', 
        'impliedVolatility': 'impliedVolatility', 
        'delta': 'pDelta', 
        'gamma': 'Gamma', 
        'theta': 'Theta', 
        'vega': 'Vega', 
        'rho': 'Rho'
    }
}

def query_data(ticker):
    global OPTIONS
    global MEMORY
    global API_KEY
    global RENAME_MAP

    if ticker not in OPTIONS:
        url = f"https://eodhistoricaldata.com/api/options/{ticker}.US?api_token={API_KEY}"
        response = requests.request("GET", url)

        OPTIONS[ticker] = response.json()
        OPTIONS[ticker]['expiries'] = [i['expirationDate'] for i in OPTIONS[ticker]['data']]
        OPTIONS[ticker]['options_chain'] = {}

        for sample in OPTIONS[ticker]['data']:
            opt_chain = {opt['strike']:{} for opt in sample['options']["CALL"]} if len(sample['options']["CALL"]) > len(sample['options']["PUT"]) else {opt['strike']:{} for opt in sample['options']["PUT"]}
            opt_types = ['CALL', 'PUT']
            for opt_type in opt_types:
                for opt in sample['options'][opt_type]: 
                    opt_chain[opt['strike']].update({RENAME_MAP[opt_type][k]:v for k, v in opt.items() if k in ['strike', 'bid', 'ask', 'volume', 'delta', 'gamma', 'theta', 'vega', 'rho', 'contractName']})
                    MEMORY[opt['contractName']] = opt
            
            OPTIONS[ticker]['options_chain'][sample['expirationDate']] = pd.DataFrame(list(opt_chain.values()), columns = ["Theta", "Gamma", "Rho", "Vega", "cName", "cDelta", "cVolume", "cBidP", "cTheo", "cAskP", "Strike", "pBidP", "pTheo", "pAskP", "pVolume", "pDelta", 'pName'])
    
    return OPTIONS[ticker]['data']

class Option:
    def __init__(self, contract_name, memory={}):
        self.contract_name = contract_name
        self.ticker = ""
        self.generate_ticker()

        query_data(self.ticker)

        if memory:
            self.memory = {contract_name: memory}
        else:
            self.memory = MEMORY
        
        self.stock_price = OPTIONS[self.ticker]['lastTradePrice']

        self.opt_type = self.memory[contract_name]['type']
        self.exercise_price =  self.memory[contract_name]['strike']
        self.time_to_expiration =  self.memory[contract_name]['daysBeforeExpiration']

        self.volatility = self.get_annualised_log_returns(self.ticker)
        self.interest_rate = 0.0192 # 10 Year Treasury rate as at Feb 18 2022

        self.price = self.black_scholes_calculate()

    def generate_ticker(self):
        for i in self.contract_name:
            if i.isalpha():
                self.ticker += i
            else: break

    def get_annualised_log_returns(self, ticker):
        """Annualised Log Return (of Underlying) - Getting sigma from black scholes"""
        local_path = f'data/historical_prices/{ticker}_historical_data.csv'
        if not os.path.exists(local_path):
            url = f"https://eodhistoricaldata.com/api/eod/{ticker}.US?api_token={API_KEY}"
            response = requests.request("GET", url)
            if not response.ok:
                raise ConnectionError(f"Code: {response.code} - {response.text}")
            with open(local_path, 'w') as f:
                f.write(response.text)
        df = pd.read_csv(local_path)
        dfa = df.dropna().iloc[len(df)-252:len(df)]
        return sum([math.log(row['Close']/dfa.loc[i-1]['Close']) for i, row, in dfa.iterrows() if i != dfa.iloc[0].name])

    def black_scholes_calculate(self):
        d1 = (math.log(self.stock_price/self.exercise_price) + (self.interest_rate + (self.volatility**2)/2) * self.time_to_expiration) / (self.volatility * math.sqrt(self.time_to_expiration))
        d2 = d1 - (self.volatility * math.sqrt(self.time_to_expiration))
        call_price = (self.stock_price * norm.cdf(d1)) - (self.exercise_price * math.exp(-self.interest_rate * self.time_to_expiration) * norm.cdf(d2))
        put_price = -(self.stock_price * norm.cdf(-d1)) + (self.exercise_price * math.exp(-self.interest_rate * self.time_to_expiration) * norm.cdf(-d2))
        if self.opt_type == "CALL":
            return call_price
        return put_price

class OptionByChoice:
    def __init__(self, ticker, opt_type, strike, expiration):
        self.data = query_data(ticker)
        self.strike = strike
        self.expiration = expiration

        opts_date = self.find_opt_date()
        self.opt_data = self.find_opt(opts_date['options'][opt_type])
        self.option = Option(self.opt_data['contractName'], memory=self.opt_data)

    def find_opt_date(self):
        for opt in self.data:
            if opt["expirationDate"] == self.expiration:
                return opt
        raise KeyError(f"No option with date: {self.expiration}")

    def find_opt(self, opts_datetype):
        for opt in opts_datetype:
            if opt['strike'] == self.strike:
                return opt
        raise KeyError(f"No option with date: {self.expiration}, strike: {self.strike}")