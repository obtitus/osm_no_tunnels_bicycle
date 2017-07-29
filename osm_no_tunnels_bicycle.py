import os
import re
import sys
import json
import pyproj
import geojson
import logging
logger = logging.getLogger('osm_no_tunnels_bicycle')

# hack
sys.path.append('../../barnehagefakta_osm')
import conflate_osm
import gentle_requests
import osmapis
import argparse_util

import elveg2osm

# this project
import util
import cycletourer
import tunnels_webpage
import merge_close_ways

def get_xml_query(query_template, bounding_box=[3.33984375, 57.468589192089325, 38.408203125, 81.1203884020757],
                  relation_id=1059668, use='relation'):
    if use == 'bounding_box':
        variables_query = ''
        area_query = '<bbox-query into="_" w="{w}" s="{s}" e="{e}" n="{n}" />'.format(w=bounding_box[0],
                                                                                      s=bounding_box[1],
                                                                                      e=bounding_box[2],
                                                                                      n=bounding_box[3])
    elif use == 'relation':
        searchArea_ref = int(relation_id)
        searchArea_ref += 3600000000 # beats me
        variables_query = '<id-query into="searchArea" ref="{ref}" type="area"/>'.format(ref=searchArea_ref)
        area_query = '<area-query from="searchArea" into="_" ref=""/>'
    else:
        raise ValueError('unkown use = "%s"', use)

    with open(args.query_template, 'r') as f:
        query = f.read()
    
    query = query.format(variables_query=variables_query,
                         area_query=area_query)
    logger.debug('XML query """%s"""', query)
    return query

def get_vegvesen_json(url=None, old_age_days=7, cache_dir='.'):
    if url is None:
        base_url = 'https://www.vegvesen.no/nvdb/api/v2'
        kartutsnitt = '&kartutsnitt=-1250478%2C5981414%2C2450478%2C8468586'
        url = base_url + '/vegobjekter/581?segmentering=true&inkluder=lokasjon%2Cegenskaper%2Cmetadata' + kartutsnitt

    
    filename = "".join(x for x in url if x.isalnum()) # https://stackoverflow.com/a/295152
    filename += '.json'
    filename = os.path.join(cache_dir, filename)
        
    cached, outdated = conflate_osm.file_util.cached_file(filename, old_age_days=old_age_days)
    if cached is not None and not(outdated):
        #print 'Using overpass responce stored as "%s". Delete this file if you want an updated version' % filename
        logger.debug('using cached %s', url)
        content = cached
    else:
        logger.debug('visiting %s', url)
        headers = {'content-type': "application/vnd.vegvesen.nvdb-v2+json"}
        params = {} #{'geometri': 'WGS84'}
        requests = gentle_requests.GentleRequests(info='osm_no_tunnels_bicycle.py')
        response = requests.get(url, timeout=300, headers=headers, params=params)
        logger.info('%s %s, status=%s', url, response, response.status_code)
        content = response.content

        # Har vi faatt det vi vil ha?
        if (response.status_code != 200):# or (headers['content-type'] not in response.headers['content-type']):
            raise ValueError(  "Expecting JSON data from the NVDB api!" +
                               "\n\tHttp status: " + str( response.status_code) +
                               "\n\tcontent: " + str( response.content) +
                               "\n\tcontent-type: " + response.headers['content-type'] )

        conflate_osm.file_util.write_file(filename, content)

    # next page?
    soup = json.loads(content)
    returned = soup['metadata']['returnert']
    next_page = soup['metadata']['neste']['href']
    if next_page == url: next_page = None
    logger.debug('vegvesen url = %s, returned %s items.\nNext = %s', url, returned, next_page)

    return soup, next_page

def get_vegvesen_all_json(url=None, *args, **kwargs):
    soup, next_page = get_vegvesen_json(url, *args, **kwargs)

    while next_page is not None:
        soup2, next_page = get_vegvesen_json(next_page, *args, **kwargs)
        soup['objekter'].extend(soup2['objekter'])
        logger.info('Now a total of %s objects', len(soup['objekter']))

    return soup['objekter']

def parse_vegvesen(json_soup):
    def get_verdi_from_list(navn, verdi=''):
        if data[u'navn'] == navn:
            if verdi != '':
                raise ValueError('Got multiple items with navn = "%s"' % navn)
            else:
                verdi = data[u'verdi']
            
        return verdi
        
    sykkelforbud = ''
    lengde = ''
    navn = ''
    merknad_syklende = ''
    for data in json_soup['egenskaper']:
        if 'navn' in data:
            sykkelforbud = get_verdi_from_list("Sykkelforbud", sykkelforbud)
            lengde = get_verdi_from_list("Lengde, skiltet", lengde)
            navn = get_verdi_from_list("Navn", navn)
            merknad_syklende = get_verdi_from_list("Merknad syklende", merknad_syklende)

    vegreferanser = json_soup['lokasjon'][u'vegreferanser'][0]['nummer']
    kategori = json_soup['lokasjon'][u'vegreferanser'][0]['kategori']
    # For europaveger tagger vi vegnummer slik: ref=E 6.
    # For riksveger og fylkesveger tagger vi vegnummer bare med tall: ref=9.
    # For kommunale og private veger og skogsbilveger tas vegnummer ikke med.
    ref = ''
    if kategori == 'E':
        ref = 'E %s' % vegreferanser
    elif kategori in ('R', 'F'):
        ref = str(vegreferanser)

    fylke = json_soup['lokasjon'][u'vegreferanser'][0]['fylke']
    wkt = json_soup['lokasjon']['geometri']['wkt']
    srid = json_soup['lokasjon']['geometri']['srid']
    reg = re.match('POINT Z \(([-+\d.]+) ([-+\d.]+) ([-+\d.]+)\)', wkt)
    wgs84 = (None, None)
    if reg:
        try:
            utm33 = map(float, reg.groups())
            projection = pyproj.Proj(init='epsg:%s' % srid)
            wgs84 = projection(utm33[0], utm33[1], inverse=True)
        except ValueError:
            logger.warning('invalid POINT Z coordinate, "%s"', wkt)
    else:
        logger.warning('invalid POINT Z coordinate, "%s"', wkt)

    lon, lat = wgs84
        
    #print vegreferanser
    return {'sykkelforbud': sykkelforbud, 'length':lengde, 'name':navn, 'comment':merknad_syklende, 'ref':ref,
            'fylke':fylke, 'lat':lat, 'lon':lon}

def convert_vegvesen_to_osm(item):
    bicycle = item['sykkelforbud'].lower()
    # note the inversion...
    if bicycle == 'ja':
        bicycle = 'no'
    elif bicycle == 'nei':
        bicycle = 'yes'
    elif bicycle is '':
        pass
    else:
        raise ValueError('unexpected bicycle tag "%s"', bicycle)

    comment = item['comment']
    if comment != '':
        comment = ' vegvesen.no: ' + comment

    length = item['length']
    if length not in (None, ''):
        note = 'Length %sm%s' % (item['length'], comment)
    else:
        note = comment.strip()
        
    tags = {'bicycle':bicycle,
            'ref': item['ref'],
            'tunnel:name': item['name'],
            'note:class:bicycle': note,
            'source':'Kartverket'}
    util.remove_empty_values(tags)

    attribs = dict()
    if item['lat'] != None and item['lon'] != None:
        attribs['lat'] = item['lat']
        attribs['lon'] = item['lon']
    
    node = osmapis.Node(attribs=attribs,
                        tags=tags)
    return node


def filter_osm_tags(tags):
    # return only relevant (tunnel, bicycle) tags
    tags = dict(tags)
    keep_tags = ['ref', 'bicycle', 'class:bicycle', 'lit', 'lit:perceived', 'note:class:bicycle',
                 'oneway', 'highway']
                 #'maxspeed', 'highway', 'surface', 'foot', 'oneway']
    #print tags.keys()
    for key in tags.keys():
        if key in keep_tags:
            continue

        if util.is_name_tag(key):
            continue
        
        # else:
        del tags[key]
    return tags
            
def simplify_osm(osm):
    merge_way_ids = list()

    osm_reduced = osmapis.OSM()
    #reduced_data = dict()
    for way_id in osm.ways:
        way = osm.ways[way_id]
        filtered_tags = filter_osm_tags(way.tags)
        #print filtered_tags
        way_copy = osmapis.Way(attribs=dict(way.attribs), tags=filtered_tags, nds=way.nds)
        #print way, way_copy
        osm_reduced.add(way_copy)

    for node_id in osm.nodes:
        osm_reduced.add(osm.nodes[node_id])

    return osm_reduced

def equal_dicts(dct1, dct2):
    if len(dct1) != len(dct2): return False
    for key in dct1:
        if key not in dct2: return False
        if dct1[key] != dct2[key]: return False
    
    return True

def discard_way_and_nodes(osm, way):
    osm.discard(way)
    for node_id in way.nds:
        # make sure we are not deleting a shared node
        for way_id, way in osm.ways.iteritems():
            if node_id in way.nds: break
        else:
            try:
                # all okay?
                osm.discard(osm.nodes[node_id])
            except KeyError:
                logger.warning('somethings fishy, node=%s does not exist', node_id)
    
def merge_oneways(osm):
    """Removes 1 close parallel one-way ways per tunnel. INPLACE!"""
    # fixme: speedup with findCloseOverlappingRoads?

    # get all oneways
    oneways = dict()
    for way_id, way in osm.ways.iteritems():
        if way.tags.get('oneway') in ('yes', '1', '-1', 'reverse'):
            oneways[way_id] = way

    logger.info('there are %s oneways tunnels', len(oneways))
    # get all identically tagged
    discarded = set()
    for way1_id, way1 in oneways.iteritems():
        if way1_id in discarded: continue
        # find identical
        candidates = list()
        for way2_id, way2 in oneways.iteritems():
            if way1_id == way2_id: continue
            if way2_id in discarded: continue
            
            if equal_dicts(way1.tags, way2.tags):
                mean, std = merge_close_ways.distance_between_ways(osm, way1, way2, break_above_distance=1e3)
                candidates.append([mean, std, way1_id, way2_id])

        # remove top candidate
        if len(candidates) != 0:
            logger.debug('candidates for way = %s, %s', way1.tags, sorted(candidates))
            
            mean, std, way1_id, way2_id = candidates[0] # prime candidate
            if mean < 30 and std < 10:
                logger.debug('Removing %s, keeping %s', way2_id, way1_id)
                del osm.ways[way1_id].tags['oneway']
                discard_way_and_nodes(osm, osm.ways[way2_id])
                discarded.add(way2_id)
                
    logger.info('of which %s oneways tunnels are most likely duplicates', len(discarded))
    return osm

def write_osm(filename, lst):
    logger.info('writing %s', filename)
    osm = osmapis.OSM()
    for item in lst:
        osm.add(item)

    osm.save(filename)
    return osm

def write_geojson(filename, lst):
    logger.info('writing %s', filename)
    features = list()
    for item in lst:
        point = geojson.Point((item.attribs['lon'], item.attribs['lat']))
        f = geojson.Feature(geometry=point, properties=item.tags)
        features.append(f)

    feature_collection = geojson.FeatureCollection(features)

    with open(filename, 'w') as f:
        geojson.dump(feature_collection, f)
    
    return feature_collection

def write_json(filename, lst):
    logger.info('writing %s', filename)
    with open(filename, 'w') as f:
        json.dump(lst, f)
    return lst

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--cycletourer_folder', default='norwegiantunnelspoi/Tunnels csv/', 
                        help='Root directory for csv data-files')
    parser.add_argument('--root', default='.', 
                        help='Root (working) directory')    
    parser.add_argument('--query_template', default="query_template.xml",
                        help="Optionally specify a overpass query xml file, defaults to query_template.xml")
    parser.add_argument('--keep_gpx_files', default=False, action='store_true',
                        help="Speed up by not deleting old gpx files")
    argparse_util.add_verbosity(parser, default=logging.DEBUG)
    
    args = parser.parse_args()
    
    delete_old_gpx = not(args.keep_gpx_files)
    root = args.root
    openstreetmap_simplified_filename = os.path.join(root, 'output', 'openstreetmap_simplified.osm')
    openstreetmap_raw_filename = os.path.join(root, 'output', 'openstreetmap_raw.osm')
    cycletourer_simplified_filename = os.path.join(root, 'output', 'cycletourer_simplified.osm')
    cycletourer_raw_filename = os.path.join(root, 'output', 'cycletourer_raw.json')
    vegvesen_simplified_filename = os.path.join(root, 'output', 'vegvesen_simplified.osm')
    vegvesen_raw_filename = os.path.join(root, 'output', 'vegvesen_raw.json')
    filenames = [openstreetmap_simplified_filename, openstreetmap_raw_filename,
                 cycletourer_simplified_filename, cycletourer_raw_filename,
                 vegvesen_simplified_filename, vegvesen_raw_filename]
    
    logging.basicConfig(level=args.loglevel)    
    

    cycletourer_data = cycletourer.get_csv_data(args.cycletourer_folder)
    write_json(cycletourer_raw_filename, cycletourer_data)
    cycletourer_osm = map(cycletourer.convert_to_osm, cycletourer_data)
    write_osm(cycletourer_simplified_filename, cycletourer_osm)
    write_geojson(cycletourer_simplified_filename.replace('.osm', '.geojson'), cycletourer_osm)
    # for item in cycletourer_osm[:10]:
    #     print item

    
    # get query
    query = get_xml_query(args.query_template) # fixme: get bounding_box from gpx files?
    # call overpass
    osm = conflate_osm.overpass_xml(xml=query, conflate_cache_filename=openstreetmap_raw_filename)
    # simplify
    osm_simple = simplify_osm(osm)
    merge_way_ids = osm.ways.keys() # simplify all ways
    elveg2osm.merge_equal(osm_simple, merge_way_ids) # join touching segments
    merge_oneways(osm_simple)                        # merge tunnels that are drawn as separate oneways
    
    osm_simple.save(openstreetmap_simplified_filename)
    osm_simple_list = osm_simple.ways.values() # fixme: support nodes as well?
    #merge_osm()
    #print osm
    # exit(1)
    
    vegvesen_objekter = get_vegvesen_all_json(cache_dir=os.path.join(root, 'cache'))
    write_json(vegvesen_raw_filename, vegvesen_objekter)
    from pprint import pprint
    pprint(vegvesen_objekter[0])
    vegvesen_forbud = map(parse_vegvesen, vegvesen_objekter)
    # fixme: divide by fylke?
    vegvesen_forbud_osm = map(convert_vegvesen_to_osm, vegvesen_forbud)
    write_osm(vegvesen_simplified_filename, vegvesen_forbud_osm)
    write_geojson(vegvesen_simplified_filename.replace('.osm', '.geojson'), vegvesen_forbud_osm)

    for item in osm_simple_list[:2]:
        print 'osm', item
    
    for item in vegvesen_forbud_osm[:2]:
        print 'vegvesen', item

    for item in cycletourer_osm[:2]:
        print 'cycletourer', item

    # for item in table[:10]: print item
    tunnels_webpage.main_index(vegvesen_forbud_osm, cycletourer_osm, osm_simple,
                               delete_old=delete_old_gpx,
                               root=root, filenames_to_link=filenames)
    # tunnels_webpage.main(vegvesen_forbud_osm, cycletourer_osm, osm_simple, root='.', filenames_to_link=filenames,
    #                      mode='cycletour',
    #                      output_html_name='cycletour_vs_osm.html')
    # tunnels_webpage.main(vegvesen_forbud_osm, cycletourer_osm, osm_simple, root='.', filenames_to_link=filenames,
    #                      mode='vegvesen_cycletour',
    #                      output_html_name='vegvesen_cycletour.html')


    
    # for way in osm.ways.values()[:2]:
    #     print way
    # for key in vegvesen_objekter[0].keys():
    #     print key, vegvesen_objekter[0][key]
    # https://www.vegvesen.no/nvdb/api/v2/vegobjekter/581?segmentering=true&inkluder=lokasjon%2Cegenskaper%2Cmetadata&kartutsnitt=-1250478%2C5981414%2C2450478%2C8468586
    # # neste
    # https://www.vegvesen.no/nvdb/api/v2/vegobjekter/581?segmentering=true&kartutsnitt=-1250478%2C5981414%2C2450478%2C8468586&start=e5Ccvrve8MPW&inkluder=lokasjon%2Cegenskaper%2Cmetadata
    # # neste
    # https://www.vegvesen.no/nvdb/api/v2/vegobjekter/581?segmentering=true&kartutsnitt=-1250478%2C5981414%2C2450478%2C8468586&start=hmddFivS4XjL&inkluder=lokasjon%2Cegenskaper%2Cmetadata
    
