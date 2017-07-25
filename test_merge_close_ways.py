import os
import math
import unittest

import logging
logger = logging.getLogger('osm_no_tunnels_bicycle.test_merge_close_ways')

import osmapis

# DUT
import merge_close_ways

root = '.'                      # fixme, get this file dir

class TestParallel950mTestCase(unittest.TestCase):
    def setUp(self):
       self.filename = os.path.join(root, 'testfiles', 'testParallel950m.osm')
       with open(self.filename, 'r') as f:
           content = f.read()
           self.osm = osmapis.OSM.from_xml(content)
           
    def test_read(self):
        self.assertEqual(len(self.osm.ways), 2)

    def get_ways(self):
        ids = sorted(self.osm.ways.keys())
        way1 = self.osm.ways[ids[0]]
        way2 = self.osm.ways[ids[1]]
        return way1, way2

    def get_nodes_way_dict(self, way):
        ret = dict()
        for nds_id in way.nds:
            ret[nds_id] = self.osm.nodes[nds_id]
        return ret

    def get_nodes_way_list(self, way):
        ret = list()
        for nds_id in way.nds:
            ret.append(self.osm.nodes[nds_id])
        return ret

    def test_nearest_node_in_way_0(self):
        way1, way2 = self.get_ways()
        node1 = self.osm.nodes[-311]
        ret = merge_close_ways.nearest_node_in_way(self.osm, node1, way2)
        self.assertEqual(ret['distance'], 0)
        self.assertEqual(ret['bearing'], 0)        

    def test_nearest_node_in_way_1(self):
        way1, way2 = self.get_ways()
        node1 = self.osm.nodes[-14]
        ret = merge_close_ways.nearest_node_in_way(self.osm, node1, way2)
        self.assertEqual(ret['node'], 0)
        
        distance = ret['distance']
        self.assertLess(abs(distance - 1050), 2)
        bearing_deg = ret['bearing']*180/math.pi
        self.assertLess(abs(bearing_deg - 90), 15)
        
    def test_distance_between_ways(self):
        way1, way2 = self.get_ways()
        # nodes1, nodes2 = self.get_nodes_way_dict(way1), self.get_nodes_way_dict(way2)
        # nodesWay1 = self.get_nodes_way_list(way1)
        mean, variance = merge_close_ways.distance_between_ways(self.osm, way1, way2)
        self.assertLess(variance, 0.5)
        self.assertLess(abs(mean - 950), 2)


class TestTwoNodes640m140degTestCase(unittest.TestCase):
    def setUp(self):
       self.filename = os.path.join(root, 'testfiles', 'twoNodes640m140deg.osm')
       with open(self.filename, 'r') as f:
           content = f.read()
           self.osm = osmapis.OSM.from_xml(content)
           
    def test_read(self):
        self.assertEqual(len(self.osm.nodes), 2)

    def get_lat_lon(self, node):
        return node.attribs['lat'], node.attribs['lon']
    
    def get_nodes_lat_lon(self):
        ids = self.osm.nodes.keys()
        node1 = self.osm.nodes[ids[0]]
        node2 = self.osm.nodes[ids[1]]
        return self.get_lat_lon(node1), self.get_lat_lon(node2)

    def test_distance(self):
        (lat1, lon1), (lat2, lon2) = self.get_nodes_lat_lon()
        logger.debug('test_distance(lat=%s, lon=%s, lat=%s, lon=%s)', lat1, lon1, lat2, lon2)
        d = merge_close_ways.lat_lon_distance(lat1, lon1, lat2, lon2)
        self.assertLess(abs(d - 640), 2)

    def test_bearing(self):
        (lat1, lon1), (lat2, lon2) = self.get_nodes_lat_lon()
        d = merge_close_ways.lat_lon_bearing(lat1, lon1, lat2, lon2)
        d_deg = d*180/math.pi   # -40
        d_pos = d_deg + 180     # 140
        self.assertLess(abs(d_pos - 140), 0.1)
        
    def test_nearest_node_in_way_1(self):
        ids = sorted(self.osm.ways.keys())
        way1 = self.osm.ways[ids[0]]

        ids = way1.nds
        node1 = self.osm.nodes[ids[0]]
        logger.debug('test_nearest_node_in_way: nodes[%s]=%s', ids[0], node1)
        ret = merge_close_ways.nearest_node_in_way(self.osm, node1, way1, minNode=1)
        self.assertLess(abs(ret['distance'] - 640), 2)

        d = ret['bearing']
        d_deg = d*180/math.pi   # -40
        # d_pos = d_deg + 180     # 140
        self.assertLess(abs(d_deg - 140), 0.1)
        
