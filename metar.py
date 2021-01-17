import requests
import xmltodict
from const import BASE_URL

class Wind:
    def __init__(self, direction, speed):
        self.dir = int(direction)
        self.speed = int(speed)

    def __repr__(self):
        return f'{self.dir} @ {self.speed:02} kts'

    def raw(self):
        return f'{self.dir:03}{self.speed:02}KT'


class CloudLayer:
    def __init__(self, sky_condition):
        self.cover = sky_condition['@sky_cover']
        if self.cover == 'CLR':
            self.alt = 0
        else:
            self.alt = sky_condition['@cloud_base_agl']


class Sky:
    def __init__(self, sky_condition):
        self.layers = []
        if len(sky_condition) == 1:
            self.layers.append(CloudLayer(sky_condition))
        else:
            for layer in sky_condition:
                self.layers.append(CloudLayer(layer))

    def ceiling(self):
        if len(self.layers) == 1:
            return self.layers[0]
        lowest = self.layers[0]
        return lowest
        # this is totally fuckered. need to find the lowest OVC or BKN layer
        # what to return if only SCT of FEW layers? 



class Metar:
    def __init__(self, metar_xml_dict):
        self.station = metar_xml_dict['station_id']
        self.obs_time = metar_xml_dict['observation_time']
        self.raw = metar_xml_dict['raw_text']
        self.temp = metar_xml_dict['temp_c']
        self.dewpt = metar_xml_dict['dewpoint_c']
        self.wind = Wind(metar_xml_dict['wind_dir_degrees'],
                         metar_xml_dict['wind_speed_kt'])
        self.vis = metar_xml_dict['visibility_statute_mi']
        self.alt = metar_xml_dict['altim_in_hg']
        self.cat =  metar_xml_dict['flight_category']
        self.sky = Sky(metar_xml_dict['sky_condition'])

    def __repr__(self):
        return f'{self.station} {self.cat}  {self.wind}  {self.vis}'





airports = "KTTA KFAY KRDU KBUY KGSO"

res = requests.get(BASE_URL + airports)

raw =[]
if res.ok:
    print('ok response')
    metars_dict = xmltodict.parse(res.text)
    results = metars_dict['response']['data']['METAR']
    n_results = int(metars_dict['response']['data']['@num_results'])
    if n_results == 1:
        raw.append(Metar(results))
    elif n_results > 1:
        for result in results:
            raw.append(Metar(result))
else:
    print('bad response')

if __name__ == '__main__':
    if raw:
        for metar in raw:
            print(metar)
