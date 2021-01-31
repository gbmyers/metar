import requests
import xmltodict
from datetime import datetime
from math import exp

# constants
BASE_URL = "https://www.aviationweather.gov/adds/dataserver_current/httpparam?" \
           "dataSource=metars&" \
           "requestType=retrieve&" \
           "format=xml&" \
           "hoursBeforeNow=5&" \
           "mostRecentForEachStation=true&" \
           "stationString="

OBS_TIME_FORMAT = '%Y-%m-%dT%H:%M:%S'

CAT_COLOR = {'LIFR': '\x1b[1;95m',  # pinkish/purple
             'IFR':  '\x1b[1;91m',  # red
             'MVFR': '\x1b[1;34m',  # blue
             'VFR':  '\x1b[1;32m'}  # green

# controls the timing and coloration of METAR timestamps based on age
TIMESTAMP_AGE = {'STALE': 20,
                 'OLD': 60}

AGE_COLOR = {'STALE': '\x1b[1;37m',  # lighter text
             'OLD': '\x1b[1;30m'}    # black text

HEADER = "ARPT TIME    CAT   WIND       ALT    TEMP     RH     VIS  CEIL/LWST   WEATHER"


class Wind:
    """ stores wind speed and direction """

    def __init__(self, direction, speed, gust=None):
        self.dir = int(direction)
        self.speed = int(speed)
        self.gust = gust

    def format_dir(self):
        # if self.dir == 0 then the direction is 'variable' (north is 360)
        return f'{self.dir:03}' if self.dir else 'VRB'

    def __repr__(self):
        wind_dir = self.format_dir()
        if not self.gust:
            return 'CALM' if self.speed == 0 else f'{wind_dir}@{self.speed:02}'
        return f'{wind_dir}@{self.speed:02}G{self.gust}'

    def raw(self):
        wind_dir = self.format_dir()
        if not self.gust:
            return f'{wind_dir}{self.speed:02}KT'
        return f'{wind_dir}{self.speed:02}G{self.gust}KT'


class CloudLayer:
    """an individual cloud layer. stores type of layer and altitude AGL"""
    # either clear skies or obscured at ground level.
    NO_LAYER = ['CLR', 'SKC', 'CAVOK', 'OVX']
    # variations on clear skies
    CLEAR = ['CLR', 'SKC', 'CAVOK']

    def __init__(self, sky_condition):
        self.cover = sky_condition['@sky_cover']
        # clear skies = no alt. obscured sky alt = 0, which makes sense
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
    """stores a list of CloudLayers.
    provides some info on ceiling and lowest layer"""

    def __init__(self, sky_condition):
        self.layers = []
        if isinstance(sky_condition, dict):
            self.layers.append(CloudLayer(sky_condition))
        else:  # should be a list.
            for layer in sky_condition:
                self.layers.append(CloudLayer(layer))

    def lowest(self):
        """ returns the lowest cloud layer or None if clear"""
        if self.layers[0].cover in CloudLayer.CLEAR:
            return None
        lowest = self.layers[0]
        for layer in self.layers:
            if layer.alt < lowest.alt:
                lowest = layer
        return lowest

    def ceiling(self):
        """returns the lowest ceiling layer or None if no ceiling"""
        if self.layers[0].cover in CloudLayer.CLEAR:
            return None
        ceiling = CloudLayer({'@sky_cover': None, '@cloud_base_ft_agl': 999999})
        for layer in self.layers:
            if layer.is_ceiling() and layer.alt < ceiling.alt:
                ceiling = layer
        return None if ceiling.cover is None else ceiling

    def ceiling_or_lowest(self):
        """returns the ceiling if one exists, or else the lowest cloud layer"""
        if self.ceiling():
            return str(self.ceiling())
        return str(self.lowest()) if self.lowest() else 'CLR'

    def all_layers(self):
        """ prints out all of the layers """
        if self.layers[0].cover in CloudLayer.CLEAR:
            return 'CLR'
        all_the_layers = ""
        for layer in self.layers:
            all_the_layers += f'{str(layer)} '
        # this should be safe, because there is always at least one layer
        return all_the_layers[:-1]  # trim the trailing space

    def __repr__(self):
        return f'{self.all_layers()}'


class Metar:
    def __init__(self, metar):
        """ takes in a dictionary created from the XML output from the aviationweather.gov ADDS text service"""
        self.station = metar['station_id']
        obs_time = metar['observation_time'][:-1]  # strip trailing Z
        self.obs_time = datetime.strptime(obs_time, OBS_TIME_FORMAT)
        self.update_age()
        self.timestamp = metar['raw_text'][5:12]
        self.raw = metar['raw_text']
        self.temp = round(float(metar['temp_c'])) if 'temp_c' in metar.keys() else None
        self.dewpt = round(float(metar['dewpoint_c'])) if 'dewpoint_c' in metar.keys() else None
        if self.temp is not None and self.dewpt is not None:
            self.rh = int(100*(exp((17.625*self.dewpt)/(243.04+self.dewpt))/exp((17.625*self.temp)/(243.04+self.temp))))
        if 'wind_speed_kt' in metar.keys():
            if 'wind_gust_kt' in metar.keys():
                self.wind = Wind(metar['wind_dir_degrees'],
                                 metar['wind_speed_kt'],
                                 metar['wind_gust_kt'])
            else:
                self.wind = Wind(metar['wind_dir_degrees'],
                                 metar['wind_speed_kt'])
        else:
            self.wind = None
        self.vis = float(metar['visibility_statute_mi']) if 'visibility_statute_mi' in metar.keys() else None
        self.alt = int(float(metar['altim_in_hg']) * 100) / 100 if 'altim_in_hg' in metar.keys() else None
        self.cat = metar['flight_category']
        self.sky = Sky(metar['sky_condition']) if 'sky_condition' in metar.keys() else None
        self.wx_string = metar['wx_string'] if 'wx_string' in metar.keys() else ""

    def update_age(self):
        obs_age = datetime.utcnow() - self.obs_time
        self.obs_age = obs_age.seconds // 60  # observation age in minutes

    def temp_and_dewpt(self):
        temp = "xx"
        dewpt = "xx"
        if self.temp is not None:
            temp_sign = "M" if self.temp < 0 else ""
            temp = f'{temp_sign}{abs(self.temp):02}'
        if self.dewpt is not None:
            dewp_sign = "M" if self.dewpt < 0 else ""
            dewpt = f'{dewp_sign}{abs(self.dewpt):02}'
        return temp + '/' + dewpt

    def format_cat(self):
        return f'{CAT_COLOR[self.cat]}{self.cat:4}\x1b[0m'

    def format_vis(self):
        """colorizes the visibility based on its flight category
        (not necessarily the flight category of the airport)
        VFR >= 5 sm
        MVFR 3-5 sm
        IFR  1-3 sm
        LIFR < 1 sm """
        if self.vis >= 5:  #
            return f'{CAT_COLOR["VFR"]} {int(self.vis):02}\x1b[0m'
        elif self.vis >= 3:
            return f'{CAT_COLOR["MVFR"]} {int(self.vis):02}\x1b[0m'
        elif self.vis >= 1:
            return f'{CAT_COLOR["IFR"]} {int(self.vis):02}\x1b[0m'
        elif self.vis == .25:
            return f'{CAT_COLOR["LIFR"]}1/4\x1b[0m'
        elif self.vis == .5:
            return f'{CAT_COLOR["LIFR"]}1/2\x1b[0m'
        elif self.vis == .75:
            return f'{CAT_COLOR["LIFR"]}3/4\x1b[0m'
        return self.vis

    def format_ceiling(self):
        """ colorizes the ceiling based on its flight category
        (not necessarily the flight category of the airport)
        VFR > 3000
        MVFR 1000 - 3000
        IFR 500 - 1000
        LIFR > 500"""
        ceiling = self.sky.ceiling()
        if ceiling:
            if ceiling.alt > 3000:
                return f'{CAT_COLOR["VFR"]} {str(ceiling):9}\x1b[0m'
            elif ceiling.alt > 1000:
                return f'{CAT_COLOR["MVFR"]} {str(ceiling):9}\x1b[0m'
            elif ceiling.alt >= 500:
                return f'{CAT_COLOR["IFR"]} {str(ceiling):9}\x1b[0m'
            else:
                return f'{CAT_COLOR["LIFR"]} {str(ceiling):9}\x1b[0m'
        # if not a ceiling, then we're VFR
        return f'{CAT_COLOR["VFR"]} {str(self.sky.ceiling_or_lowest()):9}\x1b[0m'

    def format_timestamp(self):
        """ color the timestamp based on age """
        self.update_age()
        if self.obs_age > TIMESTAMP_AGE['OLD']:
            return f'{AGE_COLOR["OLD"]}{str(self.timestamp[:-1])}\x1b[0m'
        if self.obs_age > TIMESTAMP_AGE['STALE']:
            return f'{AGE_COLOR["STALE"]}{str(self.timestamp[:-1])}\x1b[0m'
        return str(self.timestamp[:-1])

    def __repr__(self):
        return f'{self.station} ' \
               f'{self.cat} ' \
               f'{str(self.wind)} ' \
               f'{self.alt} ' \
               f'{self.temp_and_dewpt()} ' \
               f'{self.vis} ' \
               f'{str(self.sky)}'

    def text_out(self):
        """ slightly more formatted version of __repr__"""
        self.update_age()
        return f'{self.station} ' \
               f'{self.format_timestamp()}  ' \
               f'{self.format_cat()}  ' \
               f'{str(self.wind):9}  ' \
               f'{self.alt:.2f}  ' \
               f'{self.temp_and_dewpt():7}  ' \
               f'{self.rh:3}%  '\
               f'{self.format_vis()}  ' \
               f'{self.format_ceiling()}  ' \
               f'{self.wx_string}'


class Metars:
    """grabs one or more metars from aviationweather.gov"""

    def __init__(self, airports):
        """airports is a list of airport IDs"""
        self.airports = []
        if not isinstance(airports, list):  # airports is probably a string
            if isinstance(airports, str):  # let's make sure
                self.airports.append(airports)  # this is the case when we get a single string
        else:  # we've got a list, make sure all elements are strings
            for airport in airports:
                if isinstance(airport, str):  # filter out anything that's not a string
                    self.airports.append(airport)

        # what if we get a list with no strings?
        if len(self.airports) == 0:
            raise TypeError('airports must be a string or a list of strings')

        self.metars_dict = {}

        self.update()

    def update(self):
        """ Gets the latest METARs for the list of airports.
        Return True if we got a good response, False if we didn't.
        As a side effect this will trim the list of airports to those that were
        updated successfully. Invalid airport are ignored by the API."""

        res = requests.get(BASE_URL + ' '.join(self.airports))
        if res.ok:
            metars_dict = xmltodict.parse(res.text)  # parse XML to dict
            n_results = int(metars_dict['response']['data']['@num_results'])
            if n_results == 0:
                return False  # got nothing back from ADDS

            # actual results are buried a few layers in
            results = metars_dict['response']['data']['METAR']

            # keep track of which airports were successful
            successful_updates = []
            if n_results == 1:  # one result will be a singleton
                successful_updates.append(results['station_id'])
                self.metars_dict[results['station_id']] = Metar(results)
            elif n_results > 1:  # multiple results will be in a list
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
        """ provides a lightly formatted output of the metars """
        out_strings = [metar.text_out() for metar in self.metars_dict.values()]
        out_strings.sort(key=lambda x: x[0:4])  # sort by airport code
        for airport_wx in out_strings:
            print(airport_wx)

    def __repr__(self):
        out = ""
        for metar in self.metars_dict.items():
            out += f'{metar[0]}: {metar[1]}\n'
        return out[:-1]  # trim off the trailing \n


if __name__ == '__main__':
    airport_list = ['KTTA', 'KSEA', 'KRDU', 'KHQM', 'KGSO', 'KPIT', 'KHND', 'KSXT']

    metars = Metars(airport_list)
    print(HEADER)
    metars.text_out()  # something
