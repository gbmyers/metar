import requests
import xmltodict

url = "https://www.aviationweather.gov/adds/dataserver_current/httpparam?dataSource=metars&requestType=retrieve&format=xml&hoursBeforeNow=1&mostRecentForEachStation=true&stationString=KTTA KFAY KRDU KBUY KGSO"
url2 = "https://www.aviationweather.gov/adds/dataserver_current/httpparam?dataSource=metars&requestType=retrieve&format=xml&stationString=PHTO&hoursBeforeNow=4"
res = requests.get(url)

raw =[]
if res.ok:
    print('ok response')
    metars_dict = xmltodict.parse(res.text)
    results = metars_dict['response']['data']['METAR']
    n_results = int(metars_dict['response']['data']['@num_results'])
    if n_results == 1:
        raw.append(results['raw_text'])
    elif n_results > 1:
        for result in results:
            raw.append(result['raw_text'])
else:
    print('bad response')
