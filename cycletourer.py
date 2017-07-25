import os
import re
import sys
import csv
import logging
logger = logging.getLogger('osm_no_tunnels_bicycle.cycletourer')

import osmapis

# this project
import util

def unicode_csv_reader(utf8_data, dialect=csv.excel, **kwargs):
    csv_reader = csv.reader(utf8_data, dialect=dialect, **kwargs)
    for row in csv_reader:
        yield [unicode(cell, 'utf-8') for cell in row]

def cleanup_string(string):
    """
    >>> cleanup_string(u', Road - ')
    u'road'
    >>> cleanup_string(u',Lighting - ')
    u'lighting'
    >>> cleanup_string(u', Length - ')
    u'length'
    >>> cleanup_string(None)
    ''
    >>> cleanup_string(' LIT ..')
    'lit'
    >>> cleanup_string('poor.')
    'poor'
    """
    if string is None: return ''
    string = string.replace(',', '')
    string = string.replace('.', '')    
    string = string.replace(' ', '')
    string = string.replace('-', '')
    string = string.lower()
    return string

def parse_csv(csvfile, cycle_status):
    """
    >>> from StringIO import StringIO
    >>> f = StringIO('6.244639,59.340839,Osbergtunnelen,", Road - ",13,", Length - ",690m,",Lighting - ",Yes,", Comment -",,", Alt Route - ",Use the old road that runs along the lake side.')
    >>> parse_csv(f, 'Red')
    [{'comment': u'Alternative route: Use the old road that runs along the lake side', 'road_name': u'13', 'name': u'Osbergtunnelen', 'cycle_status': 'Red', 'lon': 59.340839, 'length': 690, 'lighting': u'Yes', 'lat': 6.244639}]
    """
    data = list()
    csvreader = unicode_csv_reader(csvfile)
    def get_value_from_list(clean_items, items, key, default_return=None):
        try:
            ix = clean_items.index(key)
            value = items[ix+1]
        except ValueError:
            value = default_return
        return value
        
    for item in csvreader:
        lon, lat = float(item[0]), float(item[1])
        name = item[2]

        #print item
        clean_item = map(cleanup_string, item) # avoid having to search for ', Road - '
        road_name = get_value_from_list(clean_item, item, 'road')
        lighting = get_value_from_list(clean_item, item, 'lighting')
        comment = get_value_from_list(clean_item, item, 'comment')
        if comment is None: comment = ''
        
        if comment.startswith(('No comments as yet.', 'If you have cycled this tunnel')):
            comment = ''

        altroute = get_value_from_list(clean_item, item, 'altroute', default_return='')
        if altroute != '':
            altroute = altroute.strip()
            if altroute.endswith('.'): altroute = altroute[:-1]
            comment += ' Alternative route: %s' % altroute

        comment = comment.strip()

        length = get_value_from_list(clean_item, item, 'length')
        if length is not None:
            if length.lower().endswith('km'):
                length = float(length[:-2])*1000
            elif length.endswith('m'):
                try:
                    length = int(length[:-1])
                except ValueError:
                    logger.warning('invalid length "%s"', length)
            
        row = dict(lat=lat, lon=lon, name=name, length=length, road_name=road_name,
                   lighting=lighting, comment=comment, cycle_status=cycle_status)
        data.append(row)
    return data

def get_csv_data(root_csv, colors=['Green', 'Red', 'Amber', 'White']):
    """Returns a list of 'naive' dictionary data items"""
    data = list()
    for color in colors:
        filename = os.path.join(root_csv, 'Tunnels %s.csv' % color)
        with open(filename, 'rb') as f:
            d = parse_csv(f, cycle_status=color)
            data.extend(d)
    return data

def convert_to_osm(item):
    expected_keys = ['lat', 'lon', 'name', 'length', 'road_name', 'lighting', 'comment', 'cycle_status']
    for e in expected_keys:
        if e not in item:
            raise ValueError('Expected key "%s" in item, got %s', e, item)

    comment = item['comment']
    if comment != '':
        comment = ', cycletourer.co.uk: ' + comment

    bicycle = item['cycle_status'].lower()
    class_bicycle = ''
    if bicycle == 'green':
        bicycle = 'yes'
        #class_bicycle = 0
    elif bicycle == 'red':
        bicycle = 'no'
        #class_bicycle = -3
    elif bicycle == 'amber':
        bicycle = ''
        class_bicycle = "-1"
    elif bicycle == 'white':
        bicycle = ''
        pass
    else:
        raise ValueError('unexpected cycle_status "%s"', item['cycle_status'])

    lit = cleanup_string(item['lighting'])
    lit_perceived = ''
    if lit == '?' or lit == '':
        lit = ''
    elif lit == 'poor' or lit == 'yesbutpoor' or lit =='yesbutpoorlylit' or lit == 'poorlylit' or lit == 'yesbutpoor!':
        lit = 'yes'
        lit_perceived = 'poor'
    elif lit == 'goodlights':
        lit = 'yes'
        lit_perceived = 'good'
    elif lit == 'none':
        lit = 'no'
    elif lit == 'yes' or lit == 'no':
        pass                    # keep
    else:
        logger.warning('Unkown lit status "%s" "%s"', lit, item['lighting'])
        lit = ''
        #raise ValueError('Unkown lit status "%s"', lit)
    
    attribs = dict(lat=item['lat'], lon=item['lon'])

    length = item['length']
    if length not in (None, ''):
        note = 'Length %sm%s' % (item['length'], comment)
    else:
        note = comment

    ref = item['road_name']
    if ref is None: ref = ''
    if ref.lower().startswith('e'):
        ref = 'E ' + ref[1:].strip() # add a space E 6

    name = ''
    reg1 = re.match('E \d+', ref)
    reg2 = re.match('\d+', ref)
    if reg1 is None and reg2 is None:
        name = ref
        ref = ''
        
    tags = {'tunnel:name': item['name'],
            'name': name,
            'ref': ref,
            'lit': lit,
            'lit:perceived':lit_perceived,
            'bicycle': bicycle,
            'class:bicycle': class_bicycle,
            'note:class:bicycle': note,
            'source':'cycletourer.co.uk'}
    
    util.remove_empty_values(tags)
    
    node = osmapis.Node(attribs=attribs,
                        tags=tags)
    return node
