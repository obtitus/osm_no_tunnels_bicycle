#!/usr/bin/env python
# -*- coding: utf8

# Standard python imports
import os
from copy import deepcopy
from collections import defaultdict
from copy import deepcopy

import codecs
def open_utf8(filename, *args, **kwargs):
    logger.debug('open(%s, %s, %s)', filename, args, kwargs)
    return codecs.open(filename, *args, encoding="utf-8-sig", **kwargs)
import logging
logger = logging.getLogger('osm_no_tunnels_bicycle.tunnels_webpage')

# non-standard imports
import osmapis
from jinja2 import Template
from htmldiff import htmldiff
def my_htmldiff(a, b):
    # """
    # >>> my_htmldiff('yes', 'no')
    # '<span class="delete">yes</span><span class="insert">no</span>'
    # """
    d = htmldiff.HTMLMatcher(a.encode('utf8'), b.encode('utf8'),
                             accurate_mode=True)
    return d.htmlDiff(addStylesheet=False).decode('utf8')

# this project
import util
import tunnels_graphhopper

link_template = u'<a href="{href}"\ntitle="{title}">{text}</a>'
graphhopper_url = link_template.format(href='https://github.com/graphhopper/graphhopper',
                                       title='graphhoppers github page', text='graphhopper')

def create_pre_tags(dict1, ignore_keys=('category',)):
    tags = '<pre>'
    for key, value in sorted(dict1.items()):
        if key in ignore_keys: continue
        line = '%s = %s\n' % (key, value)
        tags += line
    tags += '</pre>'
    return tags

def write_template(template_input, template_output, **template_kwargs):
    with open_utf8(template_input) as f:
        template = Template(f.read())

    page = template.render(**template_kwargs)

    with open_utf8(template_output, 'w') as output:
        output.write(page)

def get_name_list(tags, add_to_value='', include_key=False):
    ret = list()
    ret_key = list()
    for key in tags:
        # should cover name, alt_name, name:no, tunnel:name and possibly some false positives
        if util.is_name_tag(key):
            ret.append(tags[key] + add_to_value)
            ret_key.append(key)

    if include_key:
        return ret, ret_key
    else:
        return ret

def exact_match(osm1, osm2, func_get=None, filter_func=None):
    if func_get is None:
        func_get = lambda x: get_name_list(x.tags) #x.tags.get('tunnel:name', '')
    if filter_func is None:
        filter_func = lambda x: len(func_get(x)) == 0
    
    match_lists = defaultdict(list)
    visited_names = set()
    for item1 in osm1:
        if filter_func(item1): continue
        
        name1 = func_get(item1) #item1.tags.get('tunnel:name', '')
        
        #assert len(name1) == 1,
        name_backup = name1[0]
        if len(name1) != 1:
            ix = 0
            while ix < len(name1):
                if not('tunnel' in name1[ix]):
                    del name1[ix]
                elif name1[ix].strip().endswith('?'):
                    del name1[ix]
                else:
                    ix += 1

            if len(name1) == 0: # VOPS! deleted too many alternative names
                logger.warning('expected a single name in osm1, got %s = %s. Using first name', item1.tags, name1)
                name1 = [name_backup]
            elif len(name1) != 1:
                logger.warning('expected a single name in osm1, got %s = %s. Using first name', item1.tags, name1)
        
        name1 = name1[0]
        if name1 in ('', None):
            continue
        elif name1 in visited_names:
            continue
        else:
            visited_names.add(name1)
        
        # find exact matching names in osm2
        for item2 in osm2:
            if name1 in func_get(item2):#item2.tags.get('tunnel:name', ''):
                match_lists[name1].append(item1)
                match_lists[name1].append(item2)

    return match_lists

def match(osm1, osm2):
    match_lists = exact_match(osm1, osm2)
    logger.info('Found %s exact name matches (with possible duplicate matching)' % len(match_lists))
    
    for name in match_lists.keys():
        match_list = match_lists[name]
        if len(match_list) == 2:
            continue # all ok, exactly 2 matching names
    
        del match_lists[name] # not ok, lets see if we can fix it
        
        logger.debug('multiple identical name matches found for %s', name)
        # create a new unique key with "name + ' ' + ref"
        filter_func = lambda x: name not in get_name_list(x.tags)
        func_get = lambda x: get_name_list(x.tags, add_to_value=' ' + x.tags.get('ref', ''))

        # for item in match_list:
        #     print name, item.tags.get('ref', ''), item.tags.get('source', '')

        match_lists_ref = exact_match(osm1, osm2, func_get, filter_func)

        for name_key in match_lists_ref:
            match_list = match_lists_ref[name_key]
            if len(match_list) == 2:
                # all ok, add to match_lists
                assert name_key not in match_lists
                match_lists[name_key] = match_list
            else:
                logger.warning('got multiple matches, fixme: do something clever')
                for item in match_list:
                    logger.warning('tags = %s', item.tags)

                assert name_key not in match_lists
                match_lists[name_key] = match_list[:2] # pick first two matches...
                #raise Exception('Vops, need some code here, handling %s' % match_list)
        
            #print name_key, match_lists_ref[name_key]
        # print ''

    # start with all elements
    unmatched_list = list()
    unmatched_list.extend(osm1)
    unmatched_list.extend(osm2)
    logger.debug('Starting with %s items', len(unmatched_list))
    # prune those present in match_lists
    ix = 0
    while len(unmatched_list) > ix:
        for match_list in match_lists.values():
            if unmatched_list[ix] in match_list:
                del unmatched_list[ix] # matched
                break
        else:                   # no match
            ix += 1

    logger.info('Found %s exact name matches and %s unmatched items' % (len(match_lists), len(unmatched_list)))
    return match_lists, unmatched_list

def flatten(matched_dict, unmatched_list):
    ret = list()
    categories = set()
    for key in matched_dict:
        for item in matched_dict[key]:
            if 'category' in item.tags:
                item.tags['category'] += ' matched'
            else:
                item.tags['category'] = 'matched'

            categories = categories.union(item.tags['category'].split())
            
            ret.append(item)

    for item in unmatched_list:
        if 'category' in item.tags:
            item.tags['category'] += ' unmatched'
        else:
            item.tags['category'] = 'unmatched'

        categories = categories.union(item.tags['category'].split())
            
        ret.append(item)

    return ret, categories

def diff(matched_dict):
    for name, match_list in matched_dict.iteritems():
        assert len(match_list) == 2

        # bicycle the same?
        bicycle1 = match_list[0].tags.get('bicycle', '')
        bicycle2 = match_list[1].tags.get('bicycle', '')
        if bicycle1 != '' and bicycle2 != '' and bicycle1 != bicycle2:
            match_list[0].tags['bicycle'] = my_htmldiff(bicycle2, bicycle1)
            match_list[1].tags['bicycle'] = my_htmldiff(bicycle1, bicycle2)

            for item in match_list:
                if 'category' in item.tags:
                    item.tags['category'] += ' matched_diff'
                else:
                    item.tags['category'] = 'matched_diff'


    return matched_dict
        

def get_all_keys(osm, keys=None):
    if keys is None:
        keys = set()
    
    for item in osm:
        keys = keys.union( item.tags.keys())

    return keys

def sort_keys(keys):
    """Sort, but arrange [category, tunnel:name, ref, <remaining in sorted order>]"""
    keys = sorted(keys)
    ix = keys.index('tunnel:name'); del keys[ix]
    ix = keys.index('ref'); del keys[ix]
    ix = keys.index('category'); del keys[ix]
    
    keys.insert(0, 'ref')
    keys.insert(0, 'tunnel:name')
    keys.insert(0, 'category')
    return keys

def create_table(osm, header, row_header='', table=None, osm_database=None, root='.'):
    if table is None:
        table = list()
    
    for item in osm:
        links = '<pre>'
        row = []

        tunnel_name = item.tags.get('tunnel:name', '') + ' ' + item.tags.get('ref', '')
        for h in header:
            value = item.tags.get(h, '')
            row.append(value)
        if row_header != '': row.append(row_header)

        # fixme: copied
        if isinstance(item, osmapis.Node):
            osm_type_str = 'node'
        elif isinstance(item, osmapis.Way):
            osm_type_str = 'way'
        elif isinstance(item, osmapis.Relation):
            osm_type_str = 'relation'
        else:
            raise ValueError('item type not recognized, %s, %s', type(item), item)

        osm_id = item.attribs['id']            
        full = ''
        if osm_type_str is not 'node':
            full = '/full'

        osm_url_api = None
        osm_url = None
        # HACK, this is currently the simple way to test if the 'id' is actually from OSM
        if isinstance(item, osmapis.Way):
            osm_url_api = '"https://www.openstreetmap.org/api/0.6/%s/%s%s"' % (osm_type_str, osm_id, full)
            osm_url = 'http://www.openstreetmap.org/%s/%s' % (osm_type_str, osm_id)

            if osm_database is not None:
                way_osm = osm_database.ways[item.id]
                
                map_id = 'map%s' % item.id
                # graphhopper
                gpx_url = '%s.gpx' % map_id
                graphhopper_gpx = os.path.join(root, 'output', gpx_url)
                
                start = osm_database.nodes[item.nds[0]]
                start = (start.attribs['lat'], start.attribs['lon'])

                end = osm_database.nodes[item.nds[-1]]
                end = (end.attribs['lat'], end.attribs['lon'])
                
                graphhopper_tracks = tunnels_graphhopper.main(output_filename=graphhopper_gpx, start=start, end=end)

                # map page, fixme: support map-page for non-ways?
                template_map = os.path.join(root, 'template', 'map.html')
                href = '%s.html' % map_id
                output_map = os.path.join(root, 'output', href)

                # INFO
                gpx_url_link = link_template.format(href=gpx_url, title='gpx fil', text=gpx_url)
                tags = create_pre_tags(way_osm.tags)
                info = '''Showing %s auto-routed bicycle routes (using %s) between the two ends of the tunnel. Download
                gpx file: %s. Openstreetmap tags:
                %s
                ''' % (len(graphhopper_tracks), graphhopper_url, gpx_url_link, tags)
                write_template(template_map, output_map, map_id=map_id, tunnel_name=tunnel_name, info=info)

                veier = 'vei'
                if len(graphhopper_tracks) > 1:
                    veier = 'veier'
                title = u'Se %s (om-)%s fra graphhopper' % (len(graphhopper_tracks), veier)
                text = u'Vis %s (om-)%s' % (len(graphhopper_tracks), veier)
                links += link_template.format(href=href, title=title, text=text)
                links += ' ' + link_template.format(href=gpx_url, title='gpx fil med graphhopper tracks', text='gpx') + '\n'

        lat = item.attribs.get('lat', '')
        lon = item.attribs.get('lon', '')
        if lat != '' and lon != '':
            if osm_url is None:
                osm_url = 'http://www.openstreetmap.org/#map=17/{lat}/{lon}'.format(lat=lat,lon=lon)
                
        if osm_url is not None:#lat != '' and lon != '':
            title = u'Se posisjonen i openstreetmap'
            text = u'Besøk på openstreetmap.org'
            links += link_template.format(href=osm_url, title=title, text=text) + '\n'

            if lat != '' and lon != '':
                href = 'http://www.openstreetmap.org/note/new#map=17/{lat}/{lon}'.format(lat=lat,lon=lon)
                title = u'Gjør openstreetmap mappere oppmerksom på feil i kartet.'
                text = 'Meld feil til OSM'
                links += link_template.format(href=href, title=title, text=text) + '\n'
            
                href = 'http://www.openstreetmap.org/edit?editor=id&lat={lat}&lon={lon}&zoom=17'.format(lat=lat,lon=lon)
                title = u'Du blir sendt til openstreetmap sin web-editor'
                text = 'Editer OSM'
                links += link_template.format(href=href, title=title, text=text)

            
        links += '</pre>'
        row.append(links)

        # hack: hide all the empty rows
        empty_row = True
        for row_item in row[1:5]:
            if row_item.strip() != '':
                #print 'not empty', row_item
                empty_row = False
                break
        
        if not(empty_row):
            table.append(row)
    
    return table

def simplify_name_key(osm):
    # fixme: make this more clever
    for item_ix in xrange(len(osm)):
        item = osm[item_ix]
        name, name_keys = get_name_list(item.tags, include_key=True)
        name = set(name)
        if len(name) != 0:
            item = deepcopy(item)
            osm[item_ix] = item # replace by copy
            item.tags['tunnel:name'] = " ".join(name)
            for key in name_keys:
                if key != 'tunnel:name':
                    del item.tags[key]
    
def main(vegvesen_forbud_osm, cycletourer_osm, osm_simple, root='.', 
         mode='vegvesen',
         heading='Comparing vegvesen and openstreetmap.org tunnel data',
         output_html_name='table.html'):

     # HACK
    if mode == 'cycletourer':
        vegvesen_forbud_osm = cycletourer_osm
    if mode != 'vegvesen_cycletourer':
        cycletourer_osm = osm_simple.ways.values()
    
    # match
    matched_vegvesen_cycletourer, unmatched_vegvesen_cycletourer = match(vegvesen_forbud_osm, cycletourer_osm)
    matched_vegvesen_cycletourer = diff(matched_vegvesen_cycletourer)
    vegvesen_cycletourer, categories_set = flatten(matched_vegvesen_cycletourer, unmatched_vegvesen_cycletourer)

    # gather all keys
    # keys = get_all_keys(vegvesen_forbud_osm)
    # keys = get_all_keys(cycletourer_osm, keys=keys)
    simplify_name_key(vegvesen_cycletourer)
    keys = get_all_keys(vegvesen_cycletourer)
    keys = sort_keys(keys)

    # # delete old tunnel-map pages
    # import glob
    # for f in glob.glob(os.path.join(root, 'output', 'map*.html')):
    #     os.remove(f)
    # # delete old gpx traces
    # import glob
    # for f in glob.glob(os.path.join(root, 'output', 'map*.gpx')):
    #     os.remove(f)
    
    # table
    table_header = keys
    table = create_table(vegvesen_cycletourer, table_header, osm_database=osm_simple, root=root) # hack
    # table = create_table(vegvesen_forbud_osm, table_header, row_header='Vegvesen')
    # table = create_table(cycletourer_osm, table_header, table=table, row_header='Cycletourer')
    table = sorted(table, key=lambda x: x[1:])
    
    # table = match_rows(table)
    
    # table page
    template_index = os.path.join(root, 'template', 'table.html')
    output_index = os.path.join(root, 'output', output_html_name)
    table_header.append('Links')

    # info = '''openstreetmap contains %s tunnels, of these %s have been matched to the vegvesen dataset.
    # ''' % 
    info = ''
    write_template(template_index, output_index, table_header=table_header, table=table, categories_set=categories_set,
                   info=info,
                   heading=heading)

        

    return table_header, table

def main_index(vegvesen_forbud_osm, cycletourer_osm, osm_simple, filenames_to_link=None, root='.', **kwargs):
    if filenames_to_link is None:
        filenames_to_link = []
    kwargs['root'] = root

    info = ''
    filename = 'vegvesen_vs_osm.html'
    title = 'Comparing vegvesen.no and openstreetmap.org tunnel data'
    mode = 'vegvesen'
    main(vegvesen_forbud_osm, cycletourer_osm, osm_simple, 
         mode=mode, heading = title, output_html_name=filename, **kwargs)
    info += '<p>View a comparison of vegvesen.no and openstreetmap.org: %s</p>\n' % link_template.format(href=filename,
                                                                                                        title=title,
                                                                                                        text='here')
    filename = 'cycletourer_vs_osm.html'
    title = 'Comparing cycletourer.co.uk and openstreetmap.org tunnel data'
    mode = 'cycletourer'
    main(vegvesen_forbud_osm, cycletourer_osm, osm_simple, 
         mode=mode, heading = title, output_html_name=filename, **kwargs)
    info += '<p>View a comparison of cycletourer.co.uk and openstreetmap.org: %s</p>\n' % link_template.format(href=filename,
                                                                                                        title=title,
                                                                                                        text='here')

    filename = 'vegvesen_cycletourer.html'
    title = 'Comparing vegvesen and cycletourer.co.uk tunnel data'
    mode = 'vegvesen_cycletourer'
    main(vegvesen_forbud_osm, cycletourer_osm, osm_simple, 
         mode=mode, heading = title, output_html_name=filename, **kwargs)
    info += '<p>View a comparison of cycletourer.co.uk and vegvesen.no: %s</p>\n' % link_template.format(href=filename,
                                                                                                        title=title,
                                                                                                        text='here')
    # main page
    template_index = os.path.join(root, 'template', 'index.html')
    output_index = os.path.join(root, 'output', 'index.html')

    # info = '''openstreetmap contains %s tunnels, of these %s have been matched to the vegvesen dataset.
    # ''' % 
    info += '<p>The raw data can be found in the following files:</p>'
    for ix, f in enumerate(filenames_to_link):
        f = os.path.basename(f)
        href = f
        title = f
        text = f
        info += '<p>%s</p>\n' % link_template.format(href=href, title=title, text=text)

    info += '<p>For additional vegvesen data, please go to %s</p>' % link_template.format(href="https://www.vegvesen.no/vegkart/vegkart/#kartlag:geodata/hva:(~(id:67,filter:(~),farge:'1_1),(id:581,filter:(~),farge:'2_0))/@600000,7225000,3",
                                                                                          title=u'Søk etter tunneløp og tunneler på vegvesen.no',
                                                                                          text='vegvesen.no/vegkart')
    write_template(template_index, output_index, 
                   info=info,
                   heading='index')
