import sys
import logging
logger = logging.getLogger('osm_no_tunnels_bicycle.tunnels_graphhopper')

import requests
import gpxpy
import geojson

# hack
sys.path.append('../../barnehagefakta_osm')
from conflate_osm import file_util

api = 'http://localhost:8989/route?'
lat_lon_to_str = "{lat}%2C{lon}"

def request_wrap(start_str='60.394183%2C5.328369', end_str='60.628755%2C6.422882', **kwargs):
    try:
        ret = requests.get(api + 'point=%s&point=%s' % (start_str, end_str), params=kwargs)
    except requests.exceptions.ConnectionError:
        raise requests.exceptions.ConnectionError('Is graphhopper running?')
    return ret
    #http://localhost:8989/route?point=60.394183%2C5.328369&point=60.628755%2C6.422882&vehicle=bike2&ch.disable=true&alternative_route.max_paths=8&instructions=false&round_trip.seed=42&alternative_route.max_weight_factor=2&alternative_route.max_share_factor=0.9&type=gpx&gpx.route=false

def request_route(start, end, vehicle='bike', weighting='fastest'):
    params = {'vehicle':vehicle,
              'weighting':weighting,
              'ch.disable':'true',
              'alternative_route.max_paths':'8',
              'instructions':'false',
              'alternative_route.max_weight_factor':'10',
              'alternative_route.max_share_factor':'0.99',
              'type':'gpx',
              'gpx.route':'false'}
    start_str = lat_lon_to_str.format(lat=start[0], lon=start[1])
    end_str = lat_lon_to_str.format(lat=end[0], lon=end[1])
    ret = request_wrap(start_str, end_str, **params)
    xml = ret.content

    gpx = gpxpy.parse(xml)
    return gpx

def track_equality(track1, track2):
    try:
        for seg_ix in xrange(len(track1.segments)):
            seg1 = track1.segments[seg_ix]
            seg2 = track2.segments[seg_ix]
            for point_ix in xrange(len(seg1.points)):
                point1 = seg1.points[point_ix]
                point2 = seg2.points[point_ix]
                # point2_reverse = seg2.points[-1-point_ix]
                if point1.latitude != point2.latitude: #and point1.latitude != point2_reverse.latitude:
                    return False
                elif point1.longitude != point2.longitude: #and point1.longitude != point2_reverse.longitude:
                    return False
                
                # if str() != str(seg2.points[point_ix]):
                #     
        
    except IndexError:
        return False

    return True

def merge_gpx(gpx1, gpx2):
    # append tracks from gpx2 into gpx1 if they are unique, inplace!
    for track2 in gpx2.tracks:
        for track1 in gpx1.tracks:
            if track_equality(track1, track2):
                break            # no need, already present
        else:
            logger.info('Adding track %s', track2)
            gpx1.tracks.append(track2)
    
def get_all(start, end, gpx=None):
    for weighting in ('fastest', 'shortest'):
        for vehicle in ('bike', 'bike2', 'mtb', 'racingbike'):
            gpx2 = request_route(start, end, vehicle, weighting)
            if gpx is None:     # first iter
                gpx = gpx2
            else:
                merge_gpx(gpx, gpx2)
    return gpx

def write_gpx_to_geojson(filename, gpx):
    features = list()
    for track in gpx.tracks:
        points = list()
        for p in track.segments[0].points:
            points.append((p.longitude, p.latitude))
            
        line = geojson.LineString(points)
        features.append(geojson.Feature(geometry=line))

    feature_collection = geojson.FeatureCollection(features)
    ## Mapbox specific?
    #source = dict(data=feature_collection, type='geojson')
    #layer = dict(source=source, type='line', id='route') # layout={'line-join':'round', 'line-cap':'round'}, paint={'line-color': '#888', 'line-width':8}
    
    with open(filename, 'w') as f:
        geojson.dump(feature_collection, f, sort_keys=True, indent=4, separators=(',', ': '))

    return feature_collection

def remove_equal_start_stop(gpx):
    """Removes any sily tracks with either 1 point, or 2 points on the same location.
    """
    for track in gpx.tracks:
        remove = False
        if len(track.segments[0].points) > 1:
            remove = True
        elif len(track.segments[0].points) > 2:
            p0 = track.segments[0].points[0]
            p1 = track.segments[0].points[1]
            if p0.lat == p1.lat and p0.lon == p1.lon:
                remove = True

        if remove:
            track.remove = True
    return gpx
            
def main(output_filename = 'test.gpx',
         start = (59.7155, 10.8171),
         end = (59.7249, 10.8178), old_age_days=1, ret_geojson=True):

    output_filename_geojson = output_filename.replace('.gpx', '.geojson') # fixme    
    
    cached, outdated = file_util.cached_file(output_filename, old_age_days=old_age_days)
    if cached is not None and not(outdated):
        gpx = gpxpy.parse(cached)
    else:
        # Writes a number of track alternatives to output_filename, going both from
        # start to end and end to start
        gpx = get_all(start, end)
        gpx = get_all(end, start, gpx)
        gpx = remove_equal_start_stop(gpx) # removes any tracks with 2 point (or less) where start and endpoint is the same

        #if len(gpx.tracks) != 0:
        logger.info('writing %s tracks to %s', len(gpx.tracks), output_filename)
        with open(output_filename, 'w') as f:
            f.write(gpx.to_xml())

        logger.info('writing %s tracks to %s', len(gpx.tracks), output_filename_geojson)
        write_gpx_to_geojson(output_filename_geojson, gpx)

    if ret_geojson:
        with open(output_filename_geojson, 'r') as f:
            content = f.read()
        return gpx.tracks, content
    else:
        return gpx.tracks

if __name__ == '__main__':
    main(old_age_days=0)
    
                      # 'type':'gpx',
                      # 'gpx.route':

            # # gamle aasvei to ski
            # start_str = '59.7079%2C10.8336'
            # end_str = '59.7190%2C10.8386'
            # fixme: why am I not getting multiple alternatives?
            # start_str = '59.7155%2C10.8171'
            # end_str = '59.7249%2C10.8178'
            # ret = request_wrap(start_str, end_str, **params)
            # print ret
            # d = json.loads(ret.content)
            # print '='*5 + vehicle + '='*5
            # print len(d['paths']), 'alternatives'
            # for item in d['paths']:
            #     for key in item:
            #         if key not in ['points']:
            #             print key, item[key]
