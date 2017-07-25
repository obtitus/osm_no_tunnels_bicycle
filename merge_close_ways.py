"""
copied and adapted from https://github.com/tibnor/kartverket2osm
"""
import logging
logger = logging.getLogger('osm_no_tunnels_bicycle.merge_close_ways')

from math import sin, pi,fabs, sqrt
import numpy as np
import geographiclib.geodesic as gg

def linearization_of_distance(lat1, lon1, lat2, lon2):
    dlat = .001
    out = gg.Geodesic.WGS84.Inverse(lat1, lon1, lat1+dlat, lon1)
    dydlat = out["s12"]/dlat
    dlon = .001
    out = gg.Geodesic.WGS84.Inverse(lat1, lon1, lat1, lon1+dlon)
    dxdlon = out["s12"]/dlon
    #dydlat, dxdlon              # safe to cache these?
    dx = (lon2 - lon1)*dxdlon
    dy = (lat2 - lat1)*dydlat
    return dx, dy

def lat_lon_distance(lat1, lon1, lat2, lon2):
    """Calculates the distance between two points"""
    dx, dy = linearization_of_distance(lat1, lon1, lat2, lon2)
    return sqrt(dx*dx+dy*dy)

def lat_lon_bearing(lat1, lon1, lat2, lon2):
    """Calculates the bearing between two points"""
    dx, dy = linearization_of_distance(lat1, lon1, lat2, lon2)
    return np.arctan2(dx,dy)

def nearest_node_in_way(osm, node, way, minNode=0, maxNode=-1):
    """
    Calculate the distance to the closest node in way from node
    """
#   node = nodeListNewWay[node.attribs['ref']]
    lat = float(node.attribs['lat'])
    lon = float(node.attribs['lon'])
    shortestDistance = np.inf
    bearingToShortest = 0
    ixShortest = -1
    for ix, n_id in enumerate(way.nds):
        if (ix >= minNode) and (maxNode < 0 or ix < maxNode):
            n = osm.nodes[n_id]
            #logger.debug('nearest_node_in_way: check %s, nodes[%s]=%s', ix, n_id, n)
            lat2 = float(n.attribs["lat"])
            lon2 = float(n.attribs["lon"])
            distance = lat_lon_distance(lat, lon, lat2, lon2)
            if distance < shortestDistance:
                shortestDistance = distance
                bearingToShortest = lat_lon_bearing(lat, lon, lat2, lon2)
                ixShortest = ix

    assert shortestDistance < 1e100
    return {'node':ixShortest, 'distance':shortestDistance, 'bearing':bearingToShortest}

def distance_between_ways(osm, way1, way2, cropStartWay1=0, cropEndWay1=-1, break_above_distance=np.inf):
    """
    Calculate the mean and variance of the absolute distance between newWay and nodesCandidate
    """
    # Find length to nodes in way
    i = -1
    distance = []
    #nodesWay1 = nodes1#way1.nds#way1.findall("nd")
    
    if len(way1.nds) < 2 or (cropStartWay1 >= cropEndWay1 and cropEndWay1 > 0) or (cropStartWay1 is len(way1.nds) -1) :
        logger.warning('Ignoring way with one node. CropStart: %d CropEnd: %d Length: %d', cropStartWay1, cropEndWay1, len(way1.nds))
        return (1e100,1e100)
    else:
        logger.debug('Not ignoring way with one node. CropStart: %d CropEnd: %d Length: %d', cropStartWay1, cropEndWay1, len(way1.nds))
    
    #n = nodes1[osm[1].attribs['id']]
    # prevLat = float(n.attribs['lat'])
    # prevLon = float(n.attribs['lon'])
    for ix, node_id in enumerate(way1.nds):
        node = osm.nodes[node_id]
        lat = float(node.attribs['lat'])
        lon = float(node.attribs['lon'])
        if (ix > cropStartWay1) and (cropEndWay1 < 0 or ix < cropEndWay1):
            out = nearest_node_in_way(osm, node, way2)
            absDistance = fabs(out['distance'])
            # Find angle between direction to previous and nearest node
            bearingToNearestNode = out['bearing']
            bearingToPreviousNode = lat_lon_bearing(lat, lon, prevLat, prevLon)
            if i == 0:
                bearingToPreviousNode -= pi
            d = abs(sin(bearingToNearestNode-bearingToPreviousNode))*absDistance
            # logger.debug('absDistance = %.0f, bearingToNearestNode = %.0f deg, bearingToPreviousNode = %.0f deg',
            #              absDistance, bearingToNearestNode*180/pi, bearingToPreviousNode*180/pi)
            # logger.debug('distance = %s*%s = %s', sin(bearingToNearestNode-bearingToPreviousNode), absDistance, d)
            distance.append(d)
            if d > break_above_distance:
                break
            
        prevLat = lat
        prevLon = lon
    # Find mean and variance of distance between roads
    mean = np.mean(distance)
    variance = np.std(distance)
    return (mean,variance)
