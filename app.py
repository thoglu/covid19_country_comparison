# -*- coding: utf-8 -*-
import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output

import plotly.graph_objects as go

import os
import subprocess
import pandas as pd
import numpy
import math
import datetime
import time
import glob
import math
import countryinfo
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor


global_per_population=100000.0


global_data=None
dates=None
last_date=None
glob_path=""

def update_data(url="https://github.com/CSSEGISandData/COVID-19.git"):
    
    global glob_path

    print("UPD DATA .. GLOB PATH ", glob_path)
    if not os.path.exists("timeseries"):
        os.makedirs("timeseries")
        os.system("git clone %s timeseries" % url)
    else:
        os.chdir("timeseries")
        os.system("git pull")
        os.chdir("..")
    
    
    print("finished update data..")
## global variables



######################

def find_doubling_time(arr):
    """ 
    Calculates doubling time in timesteps (days). 
    """

    cur_ind=len(arr)-1
    last_ind=cur_ind
    max_ind=cur_ind

    last_ratio=1.0

    if(arr[cur_ind]==0):
        return 0

    
    while(cur_ind>0):
        last_ind=cur_ind
        cur_ind-=1

        cur_ratio=arr[cur_ind]/arr[max_ind]

        if(cur_ratio==0):
            return 0
        #if(cur_ratio > 1):
        #    return math.inf
        #print("RAT", cur_ratio)
        if(cur_ratio<=0.5): 
            #print("smaller ", cur_ind)
            frac1=0.5-cur_ratio
            frac2=last_ratio-0.5

            extra_frac=(frac1*0+frac2*1.0)/(frac1+frac2)

            return (max_ind-last_ind)+extra_frac
        else:
            last_ratio=cur_ratio

    return max_ind

def load_data(timeseries_folder="timeseries/csse_covid_19_data/csse_covid_19_time_series"):

    global global_data, dates, last_date

    confirmed=pd.read_csv(os.path.join(timeseries_folder, "time_series_19-covid-Confirmed.csv"))
    recovered=pd.read_csv(os.path.join(timeseries_folder, "time_series_19-covid-Recovered.csv"))
    died=pd.read_csv(os.path.join(timeseries_folder, "time_series_19-covid-Deaths.csv"))

    print("LOADED CSV files ...", timeseries_folder)
    num_countries=confirmed.shape[0]

    region_label=str(confirmed.columns[0])
    country_label=str(confirmed.columns[1])

    tot_counter=0

    dates=confirmed.loc[0].index[4:]

    dates=[datetime.datetime.strptime(i, "%m/%d/%y") for i in dates]
    
    all_data=dict()
    
    countryinfo_names=dict()
    countryinfo_names["Czechia"]="Czech Republic"
    countryinfo_names["Korea, South"]="South Korea"
    countryinfo_names["Taiwan*"]="Taiwan"
    countryinfo_names["US"]="United States"

    for ind in range(num_countries):
        
        #print(type(confirmed.loc[ind].at[region_label]))
        if(not type(confirmed.loc[ind].at[region_label])==float):
            if(confirmed.loc[ind].values[1]==confirmed.loc[ind].values[0]):

                print("taking ",confirmed.loc[ind].values[1] )
            elif(not (confirmed.loc[ind].values[1]=="US" or confirmed.loc[ind].values[1]=="China" or confirmed.loc[ind].values[1]=="Canada" or confirmed.loc[ind].values[1]=="Australia")):   
                print("skipping ", confirmed.loc[ind].values[1], confirmed.loc[ind].values[0])
                continue
       
        this_country=confirmed.loc[ind].values[1]
        

        #try:

        cname=this_country
        if(cname in countryinfo_names.keys()):
            cname=countryinfo_names[cname]
        
        this_country_info=countryinfo.CountryInfo(cname)

        cname=cname.lower()

        if(cname not in this_country_info.__dict__["_CountryInfo__countries"].keys()):
            print("couldnt find country ", this_country, " in countryinfo object..")
        else:
            population=this_country_info.population()
       
        if(this_country not in all_data.keys()):
            all_data[this_country]=dict()

        if("abs_total_confirmed" not in all_data[this_country].keys()):
            all_data[this_country]["abs_total_confirmed"]=0.0
        all_data[this_country]["abs_total_confirmed"]+=confirmed.loc[ind].values[4:]
        
        if("total_confirmed" not in all_data[this_country].keys()):
            all_data[this_country]["total_confirmed"]=0.0
        all_data[this_country]["total_confirmed"]=confirmed.loc[ind].values[4:]/float(population)*global_per_population
        add_one=numpy.array([0.0]+list(confirmed.loc[ind].values[4:]))

        if("daily_new_confirmed" not in all_data[this_country].keys()):
            all_data[this_country]["daily_new_confirmed"]=0.0
        all_data[this_country]["daily_new_confirmed"]+=(add_one[1:]-add_one[0:-1])/float(population)*global_per_population


        if("total_recovered" not in all_data[this_country].keys()):
            all_data[this_country]["total_recovered"]=0.0
        all_data[this_country]["total_recovered"]+=recovered.loc[ind].values[4:]/float(population)*global_per_population

        if("active_confirmed" not in all_data[this_country].keys()):
            all_data[this_country]["active_confirmed"]=0.0
        all_data[this_country]["active_confirmed"]+=(confirmed.loc[ind].values[4:]-recovered.loc[ind].values[4:])/float(population)*global_per_population
        
        if("total_died" not in all_data[this_country].keys()):
            all_data[this_country]["total_died"]=0.0
        all_data[this_country]["total_died"]+=died.loc[ind].values[4:]/float(population)*global_per_population

        tot_counter+=1

    for this_country in all_data.keys():

        ### effective R0 calculation is too error-prone and not included atm

        ## 5.5 incubation period + 2 days (testing to registration) + 2-3 days infection period prior to symptoms
        ## current testing and 3-day prior to symptoms infective period leads to higher number of days of potneital spreadding -> higher R_0
        high_days=10

        ## 5.5 incubation period + almost immediate testing and registration + 0 days infection period prior to symptoms
        ## very fast testing and optimistic infective period leads to low number of days of potneital spreadding -> lower R_0
        low_days=6

        #### EXCLUDE LAST DAY in R0 calculation and doubling time calculation to avoid incomplete statistics of last day! #####
        """
        r0_low=(all_data[this_country]["daily_new_confirmed"][:-1][-low_days:].sum()/all_data[this_country]["active_confirmed"][:-1][-low_days])
        r0_high=(all_data[this_country]["daily_new_confirmed"][:-1][-high_days:].sum()/all_data[this_country]["active_confirmed"][:-1][-high_days])

        r0_low=(all_data[this_country]["daily_new_confirmed"][:-1][-low_days:].sum()/all_data[this_country]["daily_new_confirmed"][:-1][-low_days-5:-low_days].sum())
        r0_high=(all_data[this_country]["daily_new_confirmed"][:-1][-high_days:].sum()/all_data[this_country]["daily_new_confirmed"][:-1][-high_days-5:-high_days].sum())
        """
        #all_data[this_country]["r0_low"]=r0_low
        #all_data[this_country]["r0_high"]=r0_high
        #all_data[this_country]["r0_mean"]=(r0_low+r0_high)*0.5
        
        all_data[this_country]["days_to_double"]=find_doubling_time(all_data[this_country]["active_confirmed"][:-1]) ## exclude last day which might be faulty

        add_one=numpy.array([all_data[this_country]["daily_new_confirmed"][0]]+list(all_data[this_country]["daily_new_confirmed"]))
        growth_facs=(add_one[1:]/add_one[0:-1])
        all_data[this_country]["growth_factor"]=numpy.where( numpy.isfinite(growth_facs), growth_facs, 1e-10) 



        #    tot_counter+=1

    global_data=all_data
    last_date=dates[-1]

    print("finished load data")
    #return all_data, dates
    #print(confirmed.loc[1])

# update roughly twice a day


def load_data_daily_reports(timeseries_folder="timeseries/csse_covid_19_data/csse_covid_19_daily_reports"):

    global global_data, dates, last_date

    sorted_reports=glob.glob(os.path.join(timeseries_folder, "*.csv"))
    sorted_reports.sort()

    print(sorted_reports)
    dates=[]

    all_data=dict()

    countryinfo_names=dict()
    countryinfo_names["Czechia"]="Czech Republic"
    countryinfo_names["Korea, South"]="South Korea"
    countryinfo_names["Taiwan*"]="Taiwan"
    countryinfo_names["US"]="United States"

    all_country_names=list(set(pd.read_csv(sorted_reports[-1])["Country_Region"]))
    all_country_names.sort()

    all_data=dict()
    
    countryinfo_names=dict()
    countryinfo_names["Czechia"]="Czech Republic"
    countryinfo_names["Korea, South"]="South Korea"
    countryinfo_names["Taiwan*"]="Taiwan"
    countryinfo_names["US"]="United States"

    ## non supported because of country-info non-support
    not_supported=["Andorra", "Bahamas", "Cabo Verde", "Serbia", "MS Zaandam", "Timor-Leste", "Kosovo", "Burma", "West Bank and Gaza", "North Macedonia", "Congo (Brazzaville)", "Congo (Kinshasa)", "Cote d'Ivoire", "Cruise Ship", "Diamond Princess", "Eswatini", "Montenegro", "Gambia", "Holy See"]

    double_names=dict()
    double_names["China"]="Mainland China"
    double_names["Korea, South"]="South Korea"

    for n in not_supported:
        if(n in all_country_names):
            all_country_names.remove(n)

    for file in sorted_reports:
        print("..reading ", file)
        all=pd.read_csv(file)
        region_col_name="Country/Region"
        if("Country_Region" in all.columns):
            region_col_name="Country_Region"
        
        for cname in all_country_names:

            if(cname in not_supported):
                print("cname ", cname , " not suppprted")
                continue
            found=True
            result=all[all[region_col_name]==cname]
            if(len(result)==0):
                if(cname in double_names.keys()):

                    result=all[all[region_col_name]==double_names[cname]]
                    if(len(result)==0):
                        found=False
                   
                else:
                    found=False

            if(found==False):
                
                #print(cname , " not found ")
                if(cname not in all_data.keys()):
                    all_data[cname]=dict()
                    all_data[cname]["total_confirmed"]=[0.0]
                    all_data[cname]["total_died"]=[0.0]
                    all_data[cname]["total_recovered"]=[0.0]
                else:
                    all_data[cname]["total_confirmed"].append(all_data[cname]["total_confirmed"][-1])
                    all_data[cname]["total_died"].append(all_data[cname]["total_died"][-1])
                    all_data[cname]["total_recovered"].append(all_data[cname]["total_recovered"][-1])
            else:
                if(cname not in all_data.keys()):
                    all_data[cname]=dict()
                    all_data[cname]["total_confirmed"]=[]
                    all_data[cname]["total_died"]=[]
                    all_data[cname]["total_recovered"]=[]

                #print(result)
                vals=result["Confirmed"].values
                finite=numpy.where(numpy.isfinite(vals), vals, 0)

                all_data[cname]["total_confirmed"].append(finite.sum())

                vals=result["Deaths"].values
                finite=numpy.where(numpy.isfinite(vals), vals, 0)

                all_data[cname]["total_died"].append(finite.sum())

                vals=result["Recovered"].values
                finite=numpy.where(numpy.isfinite(vals), vals, 0)

                all_data[cname]["total_recovered"].append(finite.sum())

        date_str=file.split("/")[-1][:10]
        
        dates.append(datetime.datetime.strptime("%d-%d-%d" % ( int(date_str[:2]), int(date_str[3:5]), int(date_str[7:10])), "%m-%d-%y"))

    for ind in range(len(all_data.keys())):
        
        this_country=all_country_names[ind]
  
        cname=this_country
        if(cname in countryinfo_names.keys()):
            cname=countryinfo_names[cname]
        
        this_country_info=countryinfo.CountryInfo(cname)

        cname=cname.lower()

        if(cname not in this_country_info.__dict__["_CountryInfo__countries"].keys()):
            print("couldnt find country ", this_country, " in countryinfo object..shouldnt happen")
            sys.exit(-1)
        
        population=this_country_info.population()

        #print(population)

        all_data[this_country]["total_confirmed"]=numpy.array(all_data[this_country]["total_confirmed"])
        all_data[this_country]["total_recovered"]=numpy.array(all_data[this_country]["total_recovered"])
        all_data[this_country]["total_died"]=numpy.array(all_data[this_country]["total_died"])
        all_data[this_country]["total_died_per_pop"]=numpy.array(all_data[this_country]["total_died"])/float(population)*global_per_population
        tot_num=len(all_data[this_country]["total_died"])-1
        doubling_times=[]
        for i in range(tot_num):

            doubling_times=[find_doubling_time(all_data[this_country]["total_died"][:-(i+1)])]+doubling_times ## exclude last day which might be faulty
        
        all_data[this_country]["died_days_to_double"]=numpy.array(doubling_times)


        all_data[this_country]["total_active"]=all_data[this_country]["total_confirmed"]-all_data[this_country]["total_recovered"]-all_data[this_country]["total_died"]

        """
        if("total_confirmed_per_pop" not in all_data[this_country].keys()):
            all_data[this_country]["total_confirmed_per_pop"]=0.0

        all_data[this_country]["total_confirmed_per_pop"]=all_data[this_country]["total_confirmed"]/float(population)*global_per_population
        """

        add_one=numpy.array([0.0]+list(all_data[this_country]["total_confirmed"]))
        if("daily_new_confirmed_per_pop" not in all_data[this_country].keys()):
            all_data[this_country]["daily_new_confirmed_per_pop"]=0.0
        all_data[this_country]["daily_new_confirmed_per_pop"]+=(add_one[1:]-add_one[0:-1])/float(population)*global_per_population

        """
        if("total_recovered_per_pop" not in all_data[this_country].keys()):
            all_data[this_country]["total_recovered_per_pop"]=0.0
        all_data[this_country]["total_recovered"]+=recovered.loc[ind].values[4:]/float(population)*global_per_population
        """
        if("active_confirmed_per_pop" not in all_data[this_country].keys()):
            all_data[this_country]["active_confirmed_per_pop"]=0.0
        all_data[this_country]["active_confirmed_per_pop"]+=(all_data[this_country]["total_active"])/float(population)*global_per_population
        
        #print("find doublign of ", this_country)
        
        tot_num=len(all_data[this_country]["total_active"])-1
        doubling_times=[]
        for i in range(tot_num):

            doubling_times=[find_doubling_time(all_data[this_country]["total_active"][:-(i+1)])]+doubling_times ## exclude last day which might be faulty
        
        all_data[this_country]["days_to_double"]=numpy.array(doubling_times)

        #if(this_country=="Austria"):
        #    print(all_data[this_country]["active_confirmed_per_pop"][:-1])
        #    sys.exit(-1)
        add_one=numpy.array([all_data[this_country]["daily_new_confirmed_per_pop"][0]]+list(all_data[this_country]["daily_new_confirmed_per_pop"]))
        growth_facs=(add_one[1:]/add_one[0:-1])
        all_data[this_country]["growth_factor"]=numpy.where( numpy.isfinite(growth_facs), growth_facs, 1e-10) 

       
     
    global_data=all_data
    last_date=dates[-1]

    print("finished load data")

def get_new_data_every(period=40000):
    
    while True:
        time.sleep(30)
        update_data()
        load_data_daily_reports()
        print("data updated")
        time.sleep(period)




print("DASH")
app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
server = app.server
app.title="covid19 country comparison"
glob_last_best=0
glob_last_worst=0

glob_last_best_spread=0
glob_last_worst_spread=0

app_colors = {
'background': 'white',
'text': 'black'
}   
glob_path=os.getcwd()
print("GLOB PATH", glob_path)

update_data()
load_data_daily_reports()

#global_data, dates=load_data()
    
#<<<<<<< HEAD
executor = ThreadPoolExecutor(max_workers=1)
executor.submit(get_new_data_every)


dropdown_data=[]
for k in sorted(global_data.keys()):
    dropdown_data.append({"label": k+" days to double ~ %.1f" % (global_data[k]["days_to_double"][-1]), "value": k})



def get_layout():
    return  html.Div( style={"max-width": 1024}, children=[
            html.H1(children='Covid-19 visualization', style={
                'textAlign': 'center',
                'color': app_colors['text']
            }),
            html.H5(children='Select countries to compare *total currently active* and *daily new* cases.',style={
                'textAlign': 'center',
                'color': app_colors['text']
            }),
            html.P(children='Based on data from John-Hopkins University. Last date %s/%s/%s.' % (last_date.month, last_date.day, last_date.year),style={
                'textAlign': 'center',
                'color': app_colors['text']
            }),
            html.Div(style={
                'textAlign': 'center',
                'color': app_colors['text']
            },children=[
            html.A(href='https://github.com/thoglu/covid19_country_comparison', children="githup repo",style={
                
                'color': app_colors['text']
            })]),
            html.Hr(),
            html.P(children='Doubling time: Since a typical infection might take 10-14 days? a doubling time of active cases longer than 10-14 days might be an indication of soon reducing cases. (If testing is not biased, for example by fixed test size or change of test procedures). Values > 20 could be infinite. In general all values are to be taken with a grain of salt due to different data policies.',style={
                'textAlign': 'center',
                'color': app_colors['text']
            }),
            html.Div(style={
                'textAlign': 'center'}, children=[html.Strong(children='Comment: We want a doubling time > 10-14 days and effective R_0 (number of spreads per person) < 1! China, South Korea and Japan seem to be there. Japan has different non-strict measures compared to SK and China, and a different testing policy by testing according to symptoms. Italy, which has even stricter measures than Japan has a much worse doubling time (as of March 23). A guess (I am not an epidemologist): Basic face masks can have a non-negligible effect if whole population wears it, in particular due to asymptomatics.',style={
                'textAlign': 'center',
                'color': app_colors['text']
            })]),
            html.Hr(),
            html.P(children='Countries with most relaxed and critical situations based on doubling time (tot number of cases > 500)  or current per-100k people spread of the disease.',style={
                'textAlign': 'center',
                'color': app_colors['text']
            }),

            html.Div(children=[html.Div(style={'textAlign': 'center'}, children=[html.Button('Show 5 best (doubling)', id='button_best'),
        html.Button('Show 5 worst (doubling)', id='button_worst'), html.Button('Show 5 best (spread)', id='button_best_spread'), html.Button('Show 5 worst (spread)', id='button_worst_spread')]),
                dcc.Dropdown(
            id="dropdown_selection",
            options=dropdown_data,
            value=["Germany"],
            multi=True
        ),
        dcc.Checklist(
        id="checkpoints",
        options=[
            {'label': 'logarithmic y-axis', 'value': 'log'},
            {'label': 'show daily new cases', 'value': 'yes'},
        ],
        value=['log',"no"]
        ) 
         ]),
             html.H3(children='Active cases over time',style={
                'textAlign': 'center',
                'color': app_colors['text']
            }),
            dcc.Graph(
                id='graph',
                figure={
                    'data': [
                    ],
                    'layout': {
                        'title': 'Country comparison',
                        'plot_bgcolor': app_colors['background'],
                        'paper_bgcolor': app_colors['background']   
                }
            }),
            html.H3(children='Total died over time',style={
                'textAlign': 'center',
                'color': app_colors['text']
            }),
            html.Div(style={'textAlign': 'center'}, children=[html.Button('Show 5 best (doubling rate deaths)', id='button_best_died_doubling'), html.Button('Show 5 worst (doubling rate deaths)', id='button_worst_died_doubling')]),
            dcc.Graph(
                id='graph3',
                figure={
                    'data': [
                    ],
                    'layout': {
                        'title': 'Days to double over time',
                        'plot_bgcolor': app_colors['background'],
                        'paper_bgcolor': app_colors['background']   
                }
            }),
            html.H3(children='Development of "days to double" (active cases) over time',style={
                'textAlign': 'center',
                'color': app_colors['text']
            }),
            dcc.Graph(
                id='graph2',
                figure={
                    'data': [
                    ],
                    'layout': {
                        'title': 'Days to double over time',
                        'plot_bgcolor': app_colors['background'],
                        'paper_bgcolor': app_colors['background']   
                }
            }),
            
        ])


app.layout = get_layout()

   
@app.callback(
Output('dropdown_selection', 'value'),
[Input('button_best', 'n_clicks_timestamp'), Input('button_worst', 'n_clicks_timestamp'),Input('button_best_spread', 'n_clicks_timestamp'),Input('button_worst_spread', 'n_clicks_timestamp'), Input('button_best_died_doubling', 'n_clicks_timestamp'),Input('button_worst_died_doubling', 'n_clicks_timestamp')])
def update_selection(show_best_button, show_worst_button, show_best_button_spread, show_worst_button_spread, show_best_button_died_doubling, show_worst_button_died_doubling):#

    #global glob_last_best
    #global glob_last_worst
    #global glob_last_best_spread
    #global glob_last_worst_spread
    global global_data

    max_time=-9999999999
    max_index=-1

    #1st button
    if(show_best_button is not None):
        if(show_best_button>max_time):
            max_time=show_best_button
            max_index=0
    
    # 2nd button
    if(show_worst_button is not None):
        if(show_worst_button>max_time):
            max_time=show_worst_button
            max_index=1

    # 2nd button
    if(show_best_button_spread is not None):
        if(show_best_button_spread>max_time):
            max_time=show_best_button_spread
            max_index=2

    # 3rd button
    if(show_worst_button_spread is not None):
        if(show_worst_button_spread>max_time):
            max_time=show_worst_button_spread
            max_index=3

    # 4 button
    if(show_best_button_died_doubling is not None):
        if(show_best_button_died_doubling>max_time):
            max_time=show_best_button_died_doubling
            max_index=4

    # 5 button
    if(show_worst_button_died_doubling is not None):
        if(show_worst_button_died_doubling>max_time):
            max_time=show_worst_button_died_doubling
            max_index=5
    
    if(max_index==-1):
        # default at loading
        return ["China", "Korea, South", "Japan", "Germany", "Italy"]

    case_req=400
    died_req=10
    selected_names=None

    if(max_index==0):
    
        ## show best button has been pressed
       
        names=[]
        days_to_double=[]
        cum_cases=[]

        for key in global_data.keys():
            names.append(key)
            days_to_double.append(global_data[key]["days_to_double"][-1])
            cum_cases.append(global_data[key]["total_confirmed"][-1])

        days_to_double=numpy.array(days_to_double)
        names=numpy.array(names)
        cum_cases=numpy.array(cum_cases)

       
        sel_mask=(cum_cases > case_req) #numpy.isfinite(days_to_double) & 

        sorta=numpy.argsort(days_to_double[sel_mask])

        selected_names=names[sel_mask][sorta][-5:][::-1]
      

    if(max_index==1):
    
        ## show_worst_button has been pressed
       
        names=[]
        mean_r0=[]
        days_to_double=[]
        cum_cases=[]

        for key in global_data.keys():
            names.append(key)
            days_to_double.append(global_data[key]["days_to_double"][-1])
            cum_cases.append(global_data[key]["total_confirmed"][-1])

        days_to_double=numpy.array(days_to_double)
        names=numpy.array(names)
        cum_cases=numpy.array(cum_cases)

        sel_mask= (cum_cases > case_req) 

        sorta=numpy.argsort(days_to_double[sel_mask])
      
        selected_names=names[sel_mask][sorta][:5]
 
    ## spread
    if(max_index==2):
        
        ## show best button has been pressed
       
        names=[]
        cum_cases=[]

        for key in global_data.keys():
            names.append(key)
            cum_cases.append(global_data[key]["active_confirmed_per_pop"][-1])

        
        names=numpy.array(names)
        cum_cases=numpy.array(cum_cases)
       
        sorta=numpy.argsort(cum_cases)

        selected_names=names[sorta][:5]
        
    if(max_index==3):
   
        ## show_worst_button has been pressed
       
        names=[]
        cum_cases=[]

        for key in global_data.keys():
            names.append(key)
            cum_cases.append(global_data[key]["active_confirmed_per_pop"][-1])

        names=numpy.array(names)
        cum_cases=numpy.array(cum_cases)
        sorta=numpy.argsort(cum_cases)

        selected_names=names[sorta][-5:]
    
    if(max_index==4):
    
        ## show best button has been pressed
       
        names=[]
        days_to_double=[]
        cum_cases=[]

        for key in global_data.keys():
            names.append(key)
            days_to_double.append(global_data[key]["died_days_to_double"][-1])
            cum_cases.append(global_data[key]["total_died"][-1])

        days_to_double=numpy.array(days_to_double)
        names=numpy.array(names)
        cum_cases=numpy.array(cum_cases)

       
        sel_mask=(cum_cases > died_req) #numpy.isfinite(days_to_double) & 

        sorta=numpy.argsort(days_to_double[sel_mask])

        selected_names=names[sel_mask][sorta][-5:][::-1]

    if(max_index==5):
   
        ## worst died_to_double
       
        names=[]
        mean_r0=[]
        days_to_double=[]
        cum_cases=[]

        for key in global_data.keys():
            names.append(key)
            days_to_double.append(global_data[key]["died_days_to_double"][-1])
            cum_cases.append(global_data[key]["total_died"][-1])

        days_to_double=numpy.array(days_to_double)
        names=numpy.array(names)
        cum_cases=numpy.array(cum_cases)

        sel_mask= (cum_cases > died_req) 

        sorta=numpy.argsort(days_to_double[sel_mask])
      
        selected_names=names[sel_mask][sorta][:5]
        


    return selected_names
   



    ##########

            


@app.callback(
Output('graph', 'figure'),
[Input('dropdown_selection', 'value'), Input('checkpoints', 'value')])
def update_figure1(selected_input_dropdown, checkpoints_input):#
    
    global app_colors, global_data, dates

    show_daily_cases=0
    log_opt="linear"
    
    if("log" in checkpoints_input):
        log_opt="log"

    if("yes" in checkpoints_input):
        show_daily_cases=1

    data_list=[]

    colors=["red", "green", "blue", "purple", "gray", "brown", "orange", "pink", "black", "yellow"]

    print("len dates .. ", len(dates), len(global_data["Germany"]["total_confirmed"]))
    for ind, inp in enumerate(selected_input_dropdown):

        

        data_list.append(dict(
            x=dates,
            y=global_data[inp]["active_confirmed_per_pop"],
            line=dict(color=colors[ind], width=4
                          ),
            name="%s (active) / doubling time: %.1f days" % (inp, global_data[inp]["days_to_double"][-1])
            ) )
        if(show_daily_cases):
            data_list.append(dict(
                x=dates,
                y=global_data[inp]["daily_new_confirmed_per_pop"],
                line=dict(color=colors[ind], width=4,dash='dash'),
                
                name="%s (daily new)" % (inp)
                ) )

    return {
        'data': data_list,
        'layout': dict(
            xaxis={'title': 'date'},
            yaxis={"type": log_opt, 'title': '# per %s population' % str(global_per_population)},
            margin={'l': 40, 'b': 40, 't': 10, 'r': 10},
            legend={'x': 0.02, 'y': 0.98},
            hovermode='closest',
            title='',
            plot_bgcolor= app_colors['background'],
            paper_bgcolor=app_colors['background']
        )
    }


@app.callback(
Output('graph2', 'figure'),
[Input('dropdown_selection', 'value'), Input('checkpoints', 'value')])
def update_figure2(selected_input_dropdown, checkpoints_input):#
    
    global app_colors, global_data, dates

    data_list=[]

    colors=["red", "green", "blue", "purple", "gray", "brown", "orange", "pink", "black", "yellow"]

    for ind, inp in enumerate(selected_input_dropdown):

        data_list.append(dict(
            x=dates[:-1],
            y=global_data[inp]["days_to_double"],
            line=dict(color=colors[ind], width=4
                          ),
            name="%s" % (inp)
            ) )
     
    return {
        'data': data_list,
        'layout': dict(
            xaxis={'title': 'date'},
            yaxis={"type": "linear", "title": 'days to double (per date)'},
            margin={'l': 40, 'b': 40, 't': 10, 'r': 10},
            legend={'x': 0.02, 'y': 0.98},
            hovermode='closest',
            title='',
            plot_bgcolor= app_colors['background'],
            paper_bgcolor=app_colors['background']
        )
    }


@app.callback(
Output('graph3', 'figure'),
[Input('dropdown_selection', 'value'), Input('checkpoints', 'value')])
def update_figure3(selected_input_dropdown, checkpoints_input):#
    
    global app_colors, global_data, dates

    data_list=[]

    colors=["red", "green", "blue", "purple", "gray", "brown", "orange", "pink", "black", "yellow"]

    log_opt="linear"
    
    if("log" in checkpoints_input):
        log_opt="log"


    for ind, inp in enumerate(selected_input_dropdown):

        data_list.append(dict(
            x=dates[:-1],
            y=global_data[inp]["total_died_per_pop"],
            line=dict(color=colors[ind], width=4
                          ),
            name="%s (days to double tot deaths: %.1f)" % (inp, global_data[inp]["died_days_to_double"][-1])
            ) )
     
    return {
        'data': data_list,
        'layout': dict(
            xaxis={'title': 'date'},
            yaxis={"type": log_opt, 'title': '# per %s population' % str(global_per_population)},
            margin={'l': 40, 'b': 40, 't': 10, 'r': 10},
            legend={'x': 0.02, 'y': 0.98},
            hovermode='closest',
            title='',
            plot_bgcolor= app_colors['background'],
            paper_bgcolor=app_colors['background']
        )
    }



if __name__ == '__main__':

    print("before run server...")

    app.run_server(debug=True)