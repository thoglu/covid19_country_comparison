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

import countryinfo
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

def update_data(url="https://github.com/CSSEGISandData/COVID-19.git"):
    if not os.path.exists(".timeseries"):
        os.makedirs(".timeseries")

        os.system("git clone %s timeseries" % url)
    else:
        os.chdir("timeseries")
        os.system("git pull")
        os.chdir("..")

## global variables
global_per_population=100000.0


global_data=None
dates=None
last_date=None
######################

def find_doubling_time(arr):
    """ 
    Calculates doubling time in timesteps (days). 
    """

    cur_ind=len(arr)-1
    last_ind=cur_ind
    max_ind=cur_ind

    last_ratio=1.0

    while(cur_ind>0):
        last_ind=cur_ind
        cur_ind-=1

        cur_ratio=arr[cur_ind]/arr[max_ind]

        if(cur_ratio<=0.5): 

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
        

        try:

            cname=this_country
            if(cname in countryinfo_names.keys()):
                cname=countryinfo_names[cname]
            this_country_info=countryinfo.CountryInfo(cname)
            population=this_country_info.population()
        except:
            print("couldnt find country ", this_country, " in countryinfo object..")
            continue

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


    #return all_data, dates
    #print(confirmed.loc[1])

# update roughly twice a day
def get_new_data_every(period=40000):
    """Update the data every 'period' seconds"""
    while True:
        time.sleep(30)
        update_data()
        load_data()
        print("data updated")
        time.sleep(40000)

if __name__ == '__main__':

    update_data()
    load_data()
    #global_data, dates=load_data()
    
    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(get_new_data_every)

    external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

    app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

    glob_last_best=0
    glob_last_worst=0

    glob_last_best_spread=0
    glob_last_worst_spread=0

    app_colors = {
    'background': 'white',
    'text': 'black'
    }   
    dropdown_data=[]
    for k in sorted(global_data.keys()):
        dropdown_data.append({"label": k+" days to double ~ %.1f" % (global_data[k]["days_to_double"]), "value": k})

    app.layout = html.Div( style={"max-width": 800}, children=[
        html.H1(children='Covid-19 visualization', style={
            'textAlign': 'center',
            'color': app_colors['text']
        }),
        html.H5(children='Select countries to compare *total currently active* and *daily new* cases.',style={
            'textAlign': 'center',
            'color': app_colors['text']
        }),
        html.P(children='Based on data from John-Hopkins University. Last updated %s/%s/%s.' % (last_date.month, last_date.day, last_date.year),style={
            'textAlign': 'center',
            'color': app_colors['text']
        }),
        html.Hr(),
        html.P(children='Doubling time: Since a typical infection might take 10-14 days? a doubling time of active cases longer than 10-14 days is an indication of reducing cases. (If testing is not biased, for example by fixed test size or change of test procedures)',style={
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
        })
    ])
   
    @app.callback(
    Output('dropdown_selection', 'value'),
    [Input('button_best', 'n_clicks_timestamp'), Input('button_worst', 'n_clicks_timestamp'),Input('button_best_spread', 'n_clicks_timestamp'),Input('button_worst_spread', 'n_clicks_timestamp')])
    def update_selection(show_best_button, show_worst_button, show_best_button_spread, show_worst_button_spread):#

        #global glob_last_best
        #global glob_last_worst
        #global glob_last_best_spread
        #global glob_last_worst_spread

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
        
        if(max_index==-1):
            # default at loading
            return ["China", "Korea, South", "Japan", "Germany", "Italy"]

        case_req=400
        selected_names=None

        if(max_index==0):
        
            ## show best button has been pressed
           
            names=[]
            days_to_double=[]
            cum_cases=[]

            for key in global_data.keys():
                names.append(key)
                days_to_double.append(global_data[key]["days_to_double"])
                cum_cases.append(global_data[key]["abs_total_confirmed"][-1])

            days_to_double=numpy.array(days_to_double)
            names=numpy.array(names)
            cum_cases=numpy.array(cum_cases)

           
            sel_mask=numpy.isfinite(days_to_double) & (cum_cases > case_req) 

            sorta=numpy.argsort(days_to_double[sel_mask])

         

            selected_names=names[sel_mask][sorta][-5:][::-1]
            glob_last_best=show_best_button



        if(max_index==1):
        
            ## show_worst_button has been pressed
           
            names=[]
            mean_r0=[]
            days_to_double=[]
            cum_cases=[]

            for key in global_data.keys():
                names.append(key)
                days_to_double.append(global_data[key]["days_to_double"])
                cum_cases.append(global_data[key]["abs_total_confirmed"][-1])

            days_to_double=numpy.array(days_to_double)
            names=numpy.array(names)
            cum_cases=numpy.array(cum_cases)

            sel_mask=numpy.isfinite(days_to_double) & (cum_cases > case_req) 

            sorta=numpy.argsort(days_to_double[sel_mask])

            selected_names=names[sel_mask][sorta][:5]
            glob_last_worst=show_worst_button


        ## spread
        if(max_index==2):
            
            ## show best button has been pressed
           
            names=[]
            cum_cases=[]

            for key in global_data.keys():
                names.append(key)
                cum_cases.append(global_data[key]["active_confirmed"][-1])

            
            names=numpy.array(names)
            cum_cases=numpy.array(cum_cases)
           
            sorta=numpy.argsort(cum_cases)

            selected_names=names[sorta][:5]
            glob_last_best_spread=show_best_button_spread

        if(max_index==3):
       
            ## show_worst_button has been pressed
           
            names=[]
            cum_cases=[]

            for key in global_data.keys():
                names.append(key)
                cum_cases.append(global_data[key]["active_confirmed"][-1])

            names=numpy.array(names)
            cum_cases=numpy.array(cum_cases)
            sorta=numpy.argsort(cum_cases)

            selected_names=names[sorta][-5:]
            glob_last_worst_spread=show_worst_button_spread




        return selected_names





        ##########

            


    @app.callback(
    Output('graph', 'figure'),
    [Input('dropdown_selection', 'value'), Input('checkpoints', 'value')])
    def update_figure1(selected_input_dropdown, checkpoints_input):#
        
        global app_colors
    
        show_daily_cases=0
        log_opt="linear"
        
        if("log" in checkpoints_input):
            log_opt="log"

        if("yes" in checkpoints_input):
            show_daily_cases=1

        data_list=[]

        colors=["red", "green", "blue", "purple", "gray", "brown", "orange", "pink", "black", "yellow"]

        for ind, inp in enumerate(selected_input_dropdown):

            

            data_list.append(dict(
                x=dates,
                y=global_data[inp]["active_confirmed"],
                line=dict(color=colors[ind], width=4
                              ),
                name="%s (active) / doubling time: %.1f days" % (inp, global_data[inp]["days_to_double"])
                ) )
            if(show_daily_cases):
                data_list.append(dict(
                    x=dates,
                    y=global_data[inp]["daily_new_confirmed"],
                    line=dict(color=colors[ind], width=4,dash='dash'),
                    
                    name="%s (daily new)" % (inp)
                    ) )

        return {
            'data': data_list,
            'layout': dict(
                xaxis={'title': 'Date'},
                yaxis={"type": log_opt, 'title': '# per %s population' % str(global_per_population)},
                margin={'l': 40, 'b': 40, 't': 10, 'r': 10},
                legend={'x': 0.02, 'y': 0.98},
                hovermode='closest',
                title='',
                plot_bgcolor= app_colors['background'],
                paper_bgcolor=app_colors['background'],
            )
        }

    """
    @app.callback(
    Output('graph2', 'figure'),
    [Input('dropdown_selection', 'value'), Input('checkpoints', 'value')])
    def update_figure2(selected_input_dropdown, checkpoints_input):#
        
        global app_colors
    
        log_opt="linear"
        
        if("log" in checkpoints_input):
            log_opt="log"

      
        data_list=[]

        colors=["red", "green", "blue", "purple", "gray", "brown", "orange", "pink", "black", "yellow"]

        for ind, inp in enumerate(selected_input_dropdown):

            data_list.append(dict(
                x=dates,
                y=global_data[inp]["growth_factor"],
                line=dict(color=colors[ind], width=4
                              ),
                name="%s" % (inp)
                ) )
           
        return {
            'data': data_list,
            'layout': dict(
                xaxis={'title': 'Date'},
                yaxis={"type": log_opt, "title": 'growth factor'},
                margin={'l': 40, 'b': 40, 't': 10, 'r': 10},
                legend={'x': 0.02, 'y': 0.98},
                hovermode='closest',
                title='',
                plot_bgcolor= app_colors['background'],
                paper_bgcolor=app_colors['background'],  
                transition={'duration': 500}
            )
        }
    """
    app.run_server(debug=True)