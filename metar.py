import requests
import xmltodict

# constants
BASE_URL = "https://www.aviationweather.gov/adds/dataserver_current/httpparam?"\
           "dataSource=metars&"\
           "requestType=retrieve&"\
           "format=xml&"\
           "hoursBeforeNow=1&"\
           "mostRecentForEachStation=true&"\
           "stationString="


class Wind:
    ''' stores wind speed and direction '''
    def __init__(self, direction, speed, gust=None):
        self.dir = int(direction)
        self.speed = int(speed)
        self.gust = gust

    def format_dir(self):
        # if self.dir == 0 then the direction is 'variable' (north is 360)
        return f'{self.dir:03}' if self.dir else 'VRB'

    def __repr__(self):
        dir = self.format_dir()
        if not self.gust:
            return 'CALM' if self.speed == 0 else f'{dir}@{self.speed:02}'
        return f'{dir}@{self.speed:02}G{self.gust}'

    def raw(self):
        dir = self.format_dir()
        if not self.gust:
            return f'{dir}{self.speed:02}KT'
        return f'{dir}{self.speed:02}G{self.gust}KT'


class CloudLayer:
    '''an individual cloud layer. stores type of layer and altitude AGL'''
    # either clear skies or obscured at ground level.
    NO_LAYER = ['CLR', 'SKC', 'CAVOK', 'OVX']
    # variations on clear skies
    CLEAR = ['CLR', 'SKC', 'CAVOK']

    def __init__(self, sky_condition):
        self.cover = sky_condition['@sky_cover']
        self.alt = None if self.cover in self.CLEAR else int(sky_condition['@cloud_base_ft_agl'])

    def __repr__(self):
        if self.cover in self.NO_LAYER:
            return f'{self.cover}'
        return f'{self.cover}@{self.alt}'

    def is_overcast(self):
        return self.cover == 'OVC'

    def is_broken(self):
        return self.cover == 'BKN'

    def is_obscured(self):
        return self.cover == 'OVX'

    def is_ceiling(self):
        return self.is_overcast() or self.is_broken() or self.is_obscured()


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
        if self.layers[0].cover in CloudLayer.CLEAR: return None
        lowest = self.layers[0]
        for layer in self.layers:
            if layer.alt < lowest.alt:
                lowest = layer
        return lowest

    def ceiling(self):
        '''returns the lowest ceiling layer or None if no ceiling'''
        if self.layers[0].cover in CloudLayer.CLEAR: return None
        ceiling = CloudLayer({'@sky_cover': None, '@cloud_base_ft_agl': 999999})
        for layer in self.layers:
            if layer.is_ceiling() and layer.alt < ceiling.alt:
                ceiling = layer
        return None if ceiling.cover == None else ceiling

    def all_layers(self):
        if self.layers[0].cover in CloudLayer.CLEAR:
            return 'CLR'
        all_the_layers = ""
        for layer in self.layers:
            all_the_layers += f'{str(layer)} '
        # this should be save, because there is always at least one layer
        return all_the_layers[:-1]

    def ceiling_or_lowest(self):
        '''returns the ceiling if one exists, or else the lowest cloud layer'''
        if self.ceiling():
            return str(self.ceiling())
        return str(self.lowest()) if self.lowest() else 'CLR'

    def __repr__(self):
        return f'{self.all_layers()}'


class Metar:
    def __init__(self, metar_xml_dict):
        self.station = metar_xml_dict['station_id']
        self.obs_time = metar_xml_dict['observation_time']
        self.timestamp = metar_xml_dict['raw_text'][5:12]
        self.raw = metar_xml_dict['raw_text']
        self.temp = round(float(metar_xml_dict['temp_c']))
        self.dewpt = round(float(metar_xml_dict['dewpoint_c']))
        if 'wind_gust_kt' in metar_xml_dict.keys():
            self.wind = Wind(metar_xml_dict['wind_dir_degrees'],
                             metar_xml_dict['wind_speed_kt'],
                             metar_xml_dict['wind_gust_kt'])
        else:
            self.wind = Wind(metar_xml_dict['wind_dir_degrees'],
                             metar_xml_dict['wind_speed_kt'])
        self.vis = int(float(metar_xml_dict['visibility_statute_mi']))
        self.alt = int(float(metar_xml_dict['altim_in_hg'])*100)/100
        self.cat = metar_xml_dict['flight_category']
        self.sky = Sky(metar_xml_dict['sky_condition'])

    def temp_and_dewpt(self):
        temp_sign = "M" if self.temp < 0 else ""
        dewp_sign = "M" if self.dewpt < 0 else ""
        temp = f'{temp_sign}{abs(self.temp):02}'
        dewpt = f'{dewp_sign}{abs(self.dewpt):02}'
        return  temp + '/' + dewpt

    def __repr__(self):
        return f'{self.station} '\
               f'{self.cat} '\
               f'{str(self.wind)} '\
               f'{self.alt} '\
               f'{self.temp_and_dewpt()} '\
               f'{self.vis} '\
               f'{str(self.sky)}'

    def text_out(self):
        ''' slgihtly more formatted version of __repr__'''
        print(f'{self.station} '\
              f'{self.timestamp}  '\
              f'{self.cat:4}  '\
              f'{str(self.wind):9}  '\
              f'{self.alt:.2f}  '\
              f'{self.temp_and_dewpt():7}  '\
              f'{self.vis:02}  '\
              f'{str(self.sky.ceiling_or_lowest())}')


class Metars:
    '''grabs one or more metars from aviationweather.gov'''
    def __init__(self, airports):
        '''airports is a list of airport IDs'''
        self.airports = []
        if not isinstance(airports, list): # airports is probably a string
            if isinstance(airports, str):   # let's make sure
                self.airports.append(airports)     # this is the case when we get a single string
        else:    # we've got a list, make sure all elements are strings
            for airport in airports:
                if isinstance(airport, str): # filter out anything that's not a string
                    self.airports.append(airport)

        # what if we get a list with no strings?
        if len(self.airports) == 0:
            raise TypeError('airports must be a string or a list of strings')

        self.metars_dict = {}

        self.update()

    def update(self):
        ''' Gets the latest METARs for the list of airports.
        Return True if we got a good response, False if we didn't.
        As a side effect this will trim the list of airports to those that were
        updated successfully. Invalid airport are ignored by the API.'''

        res = requests.get(BASE_URL + ' '.join(self.airports))
        if res.ok:
            metars_dict = xmltodict.parse(res.text) #parse XML to dict
            # actual results are buried a few layers isn
            results = metars_dict['response']['data']['METAR']
            n_results = int(metars_dict['response']['data']['@num_results'])
            # keep track of which airports were succefful
            successful_updates=[]
            if n_results == 1: # one result will be a singleton
                successful_updates.append(results['station_id'])
                self.metars_dict[results['station_id']] = Metar(results)
            elif n_results > 1: # multiple results will be in a list
                for result in results:
                    successful_updates.append(result['station_id'])
                    self.metars_dict[result['station_id']] = Metar(result)
            # update the list of airports we've successfully updated
            self.airports = successful_updates
            return True
        else:
            # we failed to update. got a bad response from the server
            return False

    def text_out(self):
        ''' provides a lightly formatted output of the metars '''
        for metar in self.metars_dict.values():
            metar.text_out()

    def __repr__(self):
        out = ""
        for metar in self.metars_dict.items():
            out += f'{metar[0]}: {metar[1]}\n'
        return out[:-1] # trim off the trailing \n

if __name__ == '__main__':
    airports = ['KTTA', 'KSEA', 'KRDU', 'KHQM', 'KGSO', 'KPIT', 'KHND', 'KSXT']

    metars = Metars(airports)
    metars.text_out()
