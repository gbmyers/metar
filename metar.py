import requests
import xmltodict
from const import BASE_URL

airports = "KTTA KFAY KRDU KBUY KGSO"

res = requests.get(BASE_URL + airports)

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

if raw:
    for metar in raw:
        print(metar)
