import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json

class CLODataManager:
    def __init__(self, file_path='clo_data.json'):
        self.file_path = file_path
        self.data = None

        
    def load_data(self,initial_portfolio_value,current_portfolio_value,current_collateral_value,reinvestment_period_end,portfolio_was,first_coupon_date,payment_frequency,legal_maturity,run_date):
        """Load or initialize shared CLO data"""
        try:
            with open(self.file_path, 'r') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            self.data = self.initialize_defaults(initial_portfolio_value,current_portfolio_value,current_collateral_value,reinvestment_period_end,portfolio_was,first_coupon_date,payment_frequency,legal_maturity,run_date)

    def initialize_defaults(self,initial_portfolio_value,current_portfolio_value,current_collateral_value,reinvestment_period_end,portfolio_was,first_coupon_date,payment_frequency,legal_maturity,run_date):
        return {
            "deal_info": {

                "initial_portfolio_value": initial_portfolio_value,
                "current_portfolio_value": current_portfolio_value,
                "initial_collateral_value":initial_portfolio_value,
                "current_collateral_value":current_collateral_value,
                "reinvestment_period_end": reinvestment_period_end,
                "portfolio_was":portfolio_was,
                "first_coupon_date":first_coupon_date,
                "payment_frequency": payment_frequency,
                "legal_maturity":legal_maturity,
                "run_date":run_date,
            },
            "deferred_interest": {},
            "tranches":{},
            "payment_history": [],
            "coverage_test_history": {},
            "sofr":{},
            "reserve_accounts": {}
            }

    
    def update_tranche_balance(self,tranche_name, new_balance):
        self.data["tranches"][tranche_name]["Balance"]= new_balance

    def update_coverage_test(self,period,tranche_name,amount,ic_oc):
        if tranche_name not in self.data["coverage_test_history"]:
            self.data["coverage_test_history"][tranche_name] = [ {"period": 0, "amount": 0,"ic/oc":0} ]
        
        self.data["coverage_test_history"][tranche_name].append({
            "period": period,
            "amount": amount,
            "ic/oc":ic_oc
        })
    
    def add_deferred_interest(self, period, tranche_name, amount):
        if tranche_name not in self.data["deferred_interest"]:
            self.data["deferred_interest"][tranche_name] = [ {"period": 0, "amount": 0} ]

        for info in self.data["deferred_interest"][tranche_name]:
            if info["period"] == period:
                info["amount"] += amount
                return  
        self.data["deferred_interest"][tranche_name].append({
            "period": period,
            "amount": amount
        })


    def update_reserve_account(self,period,amount):
        self.data["reserve_accounts"][period]=amount

    
    def record_payment(self, period, payment_type, beneficiary, amount):
        self.data["payment_history"].append({
            "period": period,
            "type": payment_type,
            "beneficiary": beneficiary,
            "amount": amount
        })
    
    def save_data(self):
        with open(self.file_path, 'w') as f:
            json.dump(self.data, f, indent=2)


class Interestwaterfallengine:

    def __init__(self,tranche_info,interest_payment_waterfall,coverage_tests,dm,principal_waterfall_engine):
        self.tranche_info=tranche_info
        self.interest_payment_waterfall=interest_payment_waterfall
        self.coverage_tests=coverage_tests
        self.dm=dm
        self.principal_engine=principal_waterfall_engine

    def fee_mustpay(self,period,priority,interest_received):
        spread_info=self.tranche_info.set_index("Class")["Spread or coupon"].to_dict()
        curr_outstanding_collateral=self.dm.data["deal_info"]["current_collateral_value"]
        payment_due=curr_outstanding_collateral*spread_info[priority]
        amount_paid=payment_due if interest_received >= payment_due else 0
        return amount_paid


    def current_pay(self,period,sofr,pay_freq,priority,interest_received):
        default=None
        spread_info=self.tranche_info.set_index("Class")["Spread or coupon"].to_dict()
        payment_due=self.dm.data["tranches"][priority]["Balance"]*(((sofr+spread_info[priority])/100)/pay_freq)
        amount_paid=min(payment_due,interest_received)
        if payment_due>interest_received:
            default=payment_due-interest_received
            
        return {"amount_paid":amount_paid,"default":default}

    def coverage_test(self,period,sofr,pay_freq,priority,interest_received):
        amount_paid_ic=0
        amount_paid_oc=0
        interest_received_without_deduction=(self.dm.data["deal_info"]["current_collateral_value"])*((sofr+self.dm.data["deal_info"]["portfolio_was"]/100)/pay_freq)
        tests_info=self.coverage_tests.set_index("Class")[["O/C required","I/C required"]].to_dict(orient="index")
        spread_info=self.tranche_info.set_index("Class")["Spread or coupon"].to_dict()
        rank=self.tranche_info.loc[self.tranche_info["coverage_test_group"] == priority,
                                        "Rank"].unique()[0]
    

        principal_balances_of_rank=sum(info["Balance"]
                                    for info in self.dm.data["tranches"].values()
                                    if info["Rank"] <= rank)

        interest_due_of_rank=sum(v["Balance"]*(((sofr+spread_info[k])/100)/pay_freq)
                                    for k,v in self.dm.data["tranches"].items()
                                    if v["Rank"] <= rank)
        
        if principal_balances_of_rank >0 and interest_due_of_rank >0:
         
            tranche_oc_required=tests_info[priority]["O/C required"]
            tranche_ic_required=tests_info[priority]["I/C required"]
    
            current_tranche_oc=(self.dm.data["deal_info"]["current_collateral_value"]/principal_balances_of_rank)*100


            current_tranche_ic=(interest_received_without_deduction/interest_due_of_rank)*100
        
            if current_tranche_oc<tranche_oc_required:
                
                cure_required=(principal_balances_of_rank*(tranche_oc_required/100))-(principal_balances_of_rank*(current_tranche_oc/100))
                amount_paid_oc=min(interest_received,cure_required)

                self.dm.update_coverage_test(period,priority,amount_paid_oc,"oc")
                self.principal_engine.run_principal_waterfall(period,amount_paid_oc)
                interest_received-=amount_paid_oc
                
            if current_tranche_ic<tranche_ic_required:
                cure_required=(interest_due_of_rank*(tranche_ic_required/100))-(interest_due_of_rank*(current_tranche_ic/100))
                amount_paid_ic=min(interest_received,cure_required)
                self.dm.update_coverage_test(period,priority,amount_paid_ic,"ic")
                self.principal_engine.run_principal_waterfall(period,amount_paid_ic)
                interest_received-=amount_paid_ic
        


        return (amount_paid_oc,amount_paid_ic)
    
    def deferrable_interest(self,period,sofr,pay_freq,priority,interest_received):
        spread_info=self.tranche_info.set_index("Class")["Spread or coupon"].to_dict()

        payment_due=self.dm.data["tranches"][priority]["Balance"]*(((sofr+spread_info[priority])/100)/pay_freq)
        amount_paid=min(payment_due,interest_received)
        deferred_interest=max(payment_due-amount_paid,0)
        return {"amount_paid":amount_paid,"deferred_interest":deferred_interest}
    
    def accrued_interest(self,period,priority,interest_received):
        if priority in self.dm.data["deferred_interest"]:
            payment_due=self.dm.data["deferred_interest"][priority][period-1]["amount"]
            amount_paid=min(payment_due,interest_received)
            deferred_interest=max(payment_due-amount_paid,0)
        else:
            amount_paid,deferred_interest=(0,0)

        return {"amount_paid":amount_paid,"deferred_interest":deferred_interest}
    
    def residual(self, period, priority,action, interest_received):
        amount_paid=0
        if self.dm.data["tranches"][priority]["Balance"]!=0:
            equity_at_closing = float(
                self.tranche_info.loc[self.tranche_info["Class"] == priority, "Balance"].iloc[0]
            )
            cashflows = [(-equity_at_closing,0)]
            for p in self.dm.data["payment_history"]:
                if p["beneficiary"] == priority and p["type"]==action:
                    cashflows.append((p["amount"], p["period"]))
            
            freq = self.dm.data["deal_info"]["payment_frequency"] # quarterly discount factor
            r = 0.12/freq

            if len(cashflows)<=5:
                 # ~3% per quarter
                amount_paid = interest_received
                return amount_paid

            discounted_sum = sum(cf / ((1+r) ** (t)) for cf, t in cashflows)
            payment_due = (-discounted_sum) * ((1+r) ** (period))
            amount_paid = max(min(payment_due, interest_received),0)
        
        return amount_paid


    def incentive(self,period,priority,interest_received):
        amount_paid=0
        if self.dm.data["tranches"]["Subordinated notes"]["Balance"]!=0:
            amount_paid=0.20*interest_received
        return amount_paid
    
    def simple_residual(self,period,priority,action,incentive_paid,interest_received):
        amount_paid=0
        if incentive_paid!=0:
            amount_paid=interest_received

            for p in self.dm.data["payment_history"]:
                if p["beneficiary"]==priority and p["period"]==period and p["type"]==action:
                    p["amount"]+=amount_paid
        
        return amount_paid

   
        
    def run_interest_waterfall(self,period,sofr,pay_freq):
        waterfall=list(self.interest_payment_waterfall[["Payment", "Condition"]].itertuples(index=False, name=None))
        
        interest_received=self.dm.data["deal_info"]["current_collateral_value"]*(((sofr+self.dm.data["deal_info"]["portfolio_was"])/100)/pay_freq)



        for priority,action in waterfall:
            if action in ("fee/must_pay"):
                output=self.fee_mustpay(period,priority,interest_received)
                interest_received-=output
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=output)
            elif action in ["interest"]:
                output=self.current_pay(period,sofr,pay_freq,priority,interest_received)
                if output["default"]:
                    self.dm.save_data()
                    raise RuntimeError(f"STOP: senior tranche payment due / default at period {period}")
                interest_received-=output["amount_paid"]
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=output["amount_paid"])
            elif action in ["coverage_test"]:
                output=self.coverage_test(period,sofr,pay_freq,priority,interest_received)
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=sum(output))
            
            elif action in ["residual"]:
                output=self.residual(period,priority,action,interest_received)
                interest_received-=output
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=output)
        
    
            elif action in ["deferrable_interest"]:
                output=self.deferrable_interest(period,sofr,pay_freq,priority,interest_received)
                interest_received-=output["amount_paid"]
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=output["amount_paid"])
                self.dm.add_deferred_interest(period,tranche_name=priority,amount=output["deferred_interest"])

            elif action in ["accrued_interest"]:
                output=self.accrued_interest(period,priority,interest_received)
                interest_received-=output["amount_paid"]
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=output["amount_paid"])
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=output["amount_paid"])
                self.dm.add_deferred_interest(period,tranche_name=priority,amount=output["deferred_interest"])
                
            
            elif action in ["incentive"]:
                output=self.incentive(period,priority,interest_received)
                interest_received-=output
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=output)

            elif action in ["simple_residual"]:
                incentive_paid=self.incentive(period,priority,interest_received)
                output=self.simple_residual(period,priority,action,incentive_paid,interest_received)
                interest_received-=output


        self.dm.update_reserve_account(period,interest_received)
        self.dm.record_payment(period,payment_type="reserves",beneficiary="reserves",amount=interest_received)
        interest_received-=interest_received


        if interest_received != 0:
            raise ValueError(f"Waterfall error: leftover interest = {interest_received}")


class Principalwaterfallengine():

    
    def __init__(self,tranche_info,principal_payment_waterfall,dm):
        self.tranche_info=tranche_info
        self.principal_payment_waterfall=principal_payment_waterfall
        self.dm=dm

    def principal(self,period,priority,principal_received):
        
        curr_outstanding_principal=self.dm.data["tranches"][priority]["Balance"]
        amount_paid=min(principal_received,curr_outstanding_principal)
        updated_tranche_balance=curr_outstanding_principal-amount_paid
        return {"amount_paid":amount_paid,"updated_tranche_balance":updated_tranche_balance}


    def principal_deferred_interest_prorata(self,period,priority,principal_received):
        prorata_principal=0
        prorata_deferred_interest=0
        curr_outstanding_principal=self.dm.data["tranches"][priority]["Balance"]
        deferred_interest=self.dm.data["deferred_interest"][priority][period-1]["amount"]
        if curr_outstanding_principal!=0:
            prorata_principal=min((curr_outstanding_principal/(curr_outstanding_principal+deferred_interest))*principal_received,curr_outstanding_principal)
        if curr_outstanding_principal!=0:
            prorata_deferred_interest=min((deferred_interest/(curr_outstanding_principal+deferred_interest))*principal_received,curr_outstanding_principal)
        prorata_amount=prorata_principal+prorata_deferred_interest
        amount_paid=min(principal_received,prorata_amount)
        updated_tranche_balance=curr_outstanding_principal-prorata_principal
        updated_deferred_interest=deferred_interest-prorata_deferred_interest
        return {"amount_paid":amount_paid,"prorata_principal":prorata_principal,"prorata_deferred_interest":prorata_deferred_interest,
        "updated_tranche_balance":updated_tranche_balance,"updated_deferred_interest":updated_deferred_interest}

    
    def interest(self,period,priority,principal_received):
        payment_due=self.dm.data["deferred_interest"][priority][period]["amount"]
        amount_paid=min(payment_due,principal_received)
        deferred_interest=payment_due-amount_paid
        return {"amount_paid":amount_paid,"deferred_interest":deferred_interest}
        
    def run_principal_waterfall(self,period,principal_received):
        waterfall=list(self.principal_payment_waterfall[["Payment", "Condition"]].itertuples(index=False, name=None))



        for priority,action in waterfall:
            if action in ["principal"]:
                output=self.principal(period,priority,principal_received)
                principal_received-=output["amount_paid"]
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=output["amount_paid"])
                self.dm.update_tranche_balance(priority,output["updated_tranche_balance"])
            elif action in ["principal_deferred_interest"]:
                output=self.principal_deferred_interest_prorata(period,priority,principal_received)
                principal_received-=output["amount_paid"]
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=output["prorata_principal"])
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=output["prorata_deferred_interest"])
                self.dm.update_tranche_balance(priority,output["updated_tranche_balance"])
                self.dm.add_deferred_interest(period,tranche_name=priority,amount=output["prorata_deferred_interest"])

                
            elif action in ["interest"]:
                
                output=self.interest(period,priority,principal_received)
                principal_received-=output["amount_paid"]
                self.dm.record_payment(period,payment_type=action,beneficiary=priority,amount=output["amount_paid"])
                self.dm.add_deferred_interest(period+1,tranche_name=priority,amount=output["deferred_interest"])

        
        self.dm.update_reserve_account(period,principal_received)
        self.dm.record_payment(period,payment_type="reserves",beneficiary="reserves",amount=principal_received)
        principal_received-=principal_received

        self.dm.data["deal_info"]["current_portfolio_value"]=sum(tranche["Balance"] for tranche in self.dm.data["tranches"].values())
        if principal_received != 0:
            raise ValueError(f"Waterfall error: leftover principal = {principal_received}")



class CashflowEngine():
    def __init__(self,tranche_info,interest_waterfall_info,principal_payment_waterfall,coverage_test_info,dm,prepayment_rate,default_rate,inputs_dict):
        self.prepayment_rate=prepayment_rate
        self.default_rate=default_rate
        self.tranche_info=tranche_info
        self.principal_payment_waterfall=principal_payment_waterfall
        self.interest_waterfall_info=interest_waterfall_info
        self.coverage_test_info=coverage_test_info


        dm.load_data(inputs_dict["initial_portfolio_value"],inputs_dict["current_portfolio_value"],inputs_dict["current_collateral_value"],
                                           inputs_dict["reinvestment_period_end"],inputs_dict["portfolio_was"],
                                           inputs_dict["first_coupon_date"],inputs_dict["payment_frequency"],
                                           inputs_dict["legal_maturity"],inputs_dict["run_date"])
        self.dm=dm
        
        self.principal_engine=Principalwaterfallengine(self.tranche_info,self.principal_payment_waterfall,self.dm)
        self.interest_engine=Interestwaterfallengine(self.tranche_info,self.interest_waterfall_info,self.coverage_test_info,self.dm,self.principal_engine)
        self.loan_balloon_payments={20:0.30,28:0.30,35:1}


    def adjust_for_default(self,period,current_collateral_value,default_rate,tranche_info):
        default_amount=current_collateral_value*(default_rate/self.dm.data["deal_info"]["payment_frequency"])
        
        self.dm.data["deal_info"]["current_collateral_value"]-=default_amount
        risk_order=tranche_info.dropna(subset=["Preliminary rating"])
        risk_order=risk_order["Class"][-1::-1]
        for priority in risk_order:
            if default_amount<=0:
                break
            if self.dm.data["tranches"][priority]["Balance"]!=0:
                amount_to_deduct=min(self.dm.data["tranches"][priority]["Balance"],default_amount)
                updated_tranche_balance=self.dm.data["tranches"][priority]["Balance"]-amount_to_deduct
                self.dm.update_tranche_balance(priority,updated_tranche_balance)
                default_amount-=amount_to_deduct
            continue
        self.dm.data["deal_info"]["current_portfolio_value"]=sum(tranche["Balance"] for tranche in self.dm.data["tranches"].values())


    def sofr(self,periods,base_sofr = 0.053,mean_reversion = 0.0002,vol = 0.0005):
        for period in range(periods+1):
            shock = np.random.normal(0, vol)
            rate = max(0.002, base_sofr - mean_reversion + shock)
            self.dm.data["sofr"][period]=rate
        
    def adjustment_to_collateral(self,period,reinvestment_period_end):
        current_collateral_value=self.dm.data["deal_info"]["current_collateral_value"]
        self.adjust_for_default(period,current_collateral_value,self.default_rate,self.tranche_info)
        portfolio_percent_matured= self.loan_balloon_payments.get(period, 0)
        ballon_payment=self.dm.data["deal_info"]["current_collateral_value"]*portfolio_percent_matured
        prepaid_value=self.dm.data["deal_info"]["current_collateral_value"]*(self.prepayment_rate/4)
        return {"prepaid_value":prepaid_value,"balloon_payment":ballon_payment}

    
    def convert_date_to_period(self,date,first_coupon_date,payment_frequency):
        first_coupon_date=datetime.strptime(first_coupon_date, "%d/%m/%Y")
        dt = datetime.strptime(date, "%d/%m/%Y")
        if dt<=first_coupon_date:
            period=1
        else:
            interval = 12 // payment_frequency  # months per period
            diff_months = (dt.year - first_coupon_date.year) * 12 + \
                  (dt.month - first_coupon_date.month)
            period=diff_months // interval + 1
    
        return period




        
    def run(self):
        period=self.convert_date_to_period(self.dm.data["deal_info"]["run_date"],self.dm.data["deal_info"]["first_coupon_date"],self.dm.data["deal_info"]["payment_frequency"])
        end_period=self.convert_date_to_period(self.dm.data["deal_info"]["legal_maturity"],self.dm.data["deal_info"]["first_coupon_date"],self.dm.data["deal_info"]["payment_frequency"])
        reinvestment_period_end=self.dm.data["deal_info"]["reinvestment_period_end"]
        periods=(end_period-period)+1
        if len(self.dm.data["tranches"])==0 :
            df=self.tranche_info.dropna(subset=["Balance"])
            self.dm.data["tranches"]=df.set_index("Class")[["Balance","Rank"]].to_dict(orient="index")
        else:
            pass
        self.sofr(periods)
        while self.dm.data["deal_info"]["current_collateral_value"]>0:
            sofr=self.dm.data["sofr"][period-1]
            output = self.adjustment_to_collateral(period, reinvestment_period_end)
            prepaid = output["prepaid_value"]
            balloon = output["balloon_payment"]
            

            if period <= reinvestment_period_end:
                self.interest_engine.run_interest_waterfall(period,sofr,self.dm.data["deal_info"]["payment_frequency"])
                
            else:
                principal_received = prepaid + balloon
                self.interest_engine.run_interest_waterfall(period,sofr,self.dm.data["deal_info"]["payment_frequency"])
                
                self.dm.data["deal_info"]["current_collateral_value"]-=(prepaid+balloon)
                self.principal_engine.run_principal_waterfall(period, principal_received)

            period+=1
            self.dm.save_data()




tranche_info=pd.read_excel('clo_info.xlsx',sheet_name="Tranche_info")
interest_waterfall_info=pd.read_excel('clo_info.xlsx',sheet_name="Interest_waterfall")
coverage_test_info=pd.read_excel('clo_info.xlsx',sheet_name="Coverage_test")
principal_payment_waterfall=pd.read_excel('clo_info.xlsx',sheet_name="Principal_waterfall")
prepayment_rate=0.02
default_rate=0.02

inputs_dict={"initial_portfolio_value":554980000,"current_portfolio_value":554980000,"current_collateral_value":554980000,
             "reinvestment_period_end":16,"portfolio_was":3.36,"first_coupon_date":"15/01/2026",
             "payment_frequency":4,"legal_maturity":"15/12/2035","run_date":"15/12/2025"}






payment_cols = [
    "period",

    # Fees
    "Taxes and fees, and then administrative expenses (capped)._fee/must_pay",
    "To the payment of the base management fee._fee/must_pay",

    # Interest – senior to junior
    "A-1_interest",
    "A-1_principal",
    "A-2_interest",
    "A-2_principal",
    "B_interest",
    "B_principal",
    "A/B_coverage_test",
    "C_deferrable_interest"
    "C_coverage_test",
    "C_accrued_interest",
    "D-1a_deferrable_interest",
    "D-1b_deferrable_interest",
    "D-2_deferrable_interest",
    "D_coverage_test"
    "E_deferrable_interest",
    "E_coverage_test",
    "E_accrued_interest",
    "To the payment of subordinated management fees and any deferred subordinated management fees._fee/must_pay",
    "Subordinated notes_residual",
    "20% of remaining proceeds to the incentive management fee_incentive",
    "Subordinated notes_principal",
    "reserves_reserves"

]


        
if __name__=="__main__":
    dm=CLODataManager()
    cf_engine=CashflowEngine(tranche_info,interest_waterfall_info,principal_payment_waterfall,coverage_test_info,dm,prepayment_rate,default_rate,inputs_dict)
    cf_engine.run()
    with open("clo_data.json",'r') as f:
        info = json.load(f)
    payment_history_df = pd.DataFrame(info["payment_history"])
    payment_history_df["col"] = payment_history_df["beneficiary"] + "_" + payment_history_df["type"]
    payment_history_df= (
        payment_history_df.pivot_table(
            index="period",
            columns="col",
            values="amount",
            aggfunc="sum",
            fill_value=0
        )
        .reset_index())
    payment_history_df = payment_history_df.reindex(
    columns=payment_cols,
    fill_value=0
)
    
    
    rows = []
    df_coverage = pd.DataFrame(rows)
    if info["coverage_test_history"]:
        for tranche, events in info["coverage_test_history"].items():
            for event in events:
                rows.append({
                    "tranche": tranche,
                    "period": event["period"],
                    "test_type": event.get("ic/oc"),
                    "diverted_amount": event.get("amount")
                })
        df_coverage = pd.DataFrame(rows)
        df_coverage = df_coverage.sort_values(
        by=["period", "tranche", "test_type"]
        ).reset_index(drop=True)

    rows = []

    for tranche, events in info["deferred_interest"].items():
        for event in events:
            rows.append({
                "tranche": tranche,
                "period": event["period"],      # OC / IC
                "differed_amount": event.get("amount")
            })

    deferred_interest_history_df = pd.DataFrame(rows)
    deferred_interest_history_df = deferred_interest_history_df.sort_values(
    by=["period", "tranche", "differed_amount"]
    ).reset_index(drop=True)

    
    with pd.ExcelWriter("clo_outputs.xlsx", engine="xlsxwriter") as writer:
        payment_history_df.to_excel(writer, sheet_name="Payments", index=False)
        df_coverage.to_excel(writer, sheet_name="Coverage_Tests", index=False)
        deferred_interest_history_df.to_excel(writer, sheet_name="deferred_interest", index=False)
    # df_reserves.to_excel(writer, sheet_name="Reserves", index=False)
    
    

