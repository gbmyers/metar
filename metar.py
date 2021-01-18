import requests
import xmltodict
from const import BASE_URL

class Wind:
    ''' stores wind speed and direction '''
    def __init__(self, direction, speed):
        self.dir = int(direction)
        self.speed = int(speed)

    def __repr__(self):
        return 'calm' if self.speed == 0 else f'{self.dir:03}@{self.speed:02}'

    def raw(self):
        return f'{self.dir:03}{self.speed:02}KT'


class CloudLayer:
    '''an individual cloud layer. stores type of layer and altitude AGL'''
    def __init__(self, sky_condition):
        self.cover = sky_condition['@sky_cover']
        if self.cover == 'CLR':
            self.alt = None
        else:
            self.alt = int(sky_condition['@cloud_base_ft_agl'])

    def __repr__(self):
        if self.cover == 'CLR':
            return f'{self.cover}'
        return f'{self.cover}@{self.alt}'

    def is_overcast(self):
        return self.cover == 'OVC'

    def is_broken(self):
        return self.cover == 'BKN'

    def is_ceiling(self):
        return self.is_overcast() or self.is_broken()


class Sky:
    '''stores a list of CloudLayers'''
    def __init__(self, sky_condition):
        self.layers = []
        if isinstance(sky_condition, dict):
            self.layers.append(CloudLayer(sky_condition))
        else:   # should be a list.
            for layer in sky_condition:
                self.layers.append(CloudLayer(layer))

    def lowest(self):
        ''' returns the lowest cloud layer or None if clear'''
        if self.layers[0].cover == 'CLR': return None
        lowest = CloudLayer({'@sky_cover': None, '@cloud_base_ft_agl': 999999})
        for layer in self.layers:
            if layer.alt < lowest.alt:
                lowest = layer
        return None if lowest.cover == None else lowest

    def ceiling(self):
        '''returns the lowest ceiling layer or None if no ceiling'''
        if self.layers[0].cover == 'CLR': return None
        ceiling = CloudLayer({'@sky_cover': None, '@cloud_base_ft_agl': 999999})
        for layer in self.layers:
            if layer.is_ceiling() and layer.alt < ceiling.alt:
                ceiling = layer
        return ceiling

    def all_layers(self):
        if self.layers[0].cover == 'CLR':
            return 'CLR'
        all_the_layers = ""
        for layer in self.layers:
            all_the_layers += f'{str(layer)} '
        # this should be save, because there is always at least one layer
        return all_the_layers[:-1]

    def __repr__(self):
        return self.all_layers()


class Metar:
    def __init__(self, metar_xml_dict):
        self.station = metar_xml_dict['station_id']
        self.obs_time = metar_xml_dict['observation_time']
        self.timestamp = metar_xml_dict['raw_text'][5:12]
        self.raw = metar_xml_dict['raw_text']
        self.temp = round(float(metar_xml_dict['temp_c']))
        self.dewpt = round(float(metar_xml_dict['dewpoint_c']))
        self.wind = Wind(metar_xml_dict['wind_dir_degrees'],
                         metar_xml_dict['wind_speed_kt'])
        self.vis = int(float(metar_xml_dict['visibility_statute_mi']))
        self.alt = int(float(metar_xml_dict['altim_in_hg'])*100)/100
        self.cat = metar_xml_dict['flight_category']
        self.sky = Sky(metar_xml_dict['sky_condition'])

    def raw_temp(self):
        temp_sign = ""
        dewp_sign = ""
        if self.temp < 0: temp_sign = "M"
        if self.dewpt < 0: dewp_sign = "M"
        temp = f'{temp_sign}{abs(self.temp):02}'
        dewpt = f'{dewp_sign}{abs(self.dewpt):02}'
        return  temp + '/' + dewpt

    def __repr__(self):
        return f'{self.station} '\
               f'{self.timestamp}  '\
               f'{self.cat:4}  '\
               f'{self.wind}  '\
               f'{self.alt:4}  '\
               f'{self.raw_temp():7}  '\
               f'{self.vis:02}  '\
               f'{self.sky}'


airports = "KTTA KSEA KRDU KHQM KGSO KPIT KPIA"

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
