import unittest

import logging
logger = logging.getLogger('osm_no_tunnels_bicycle.test_tunnels_webpage')

import osmapis

# DUT
import tunnels_webpage

Alnestunnelen_vegvesen = u"""
<?xml version="1.0" encoding="UTF-8"?>
<osm generator="osmapis" version="0.6">
	<node id="-1954" lat="62.4800346521" lon="6.00036418203">
		<tag k="bicycle" v="yes" />
		<tag k="note:class:bicycle" v="Length 1500m vegvesen.no: G/S-Veg" />
		<tag k="ref" v="127" />
		<tag k="source" v="Kartverket" />
		<tag k="tunnel:name" v="Alnestunnelen" />
	</node>
        <node id="-1356" lat="62.4834969155" lon="6.03288848944">
		<tag k="source" v="Kartverket" />
		<tag k="tunnel:name" v="Alnestunnelen" />
	</node>
</osm>
"""

Alnestunnelen_cycletourer = u"""
<?xml version="1.0" encoding="UTF-8"?>
<osm generator="osmapis" version="0.6">
	<node id="-148" lat="62.480358" lon="5.999656">
		<tag k="bicycle" v="yes" />
		<tag k="lit" v="yes" />
		<tag k="note:class:bicycle" v="Length 1493m, cycletourer.co.uk: There is a separate cycle lane running through this tunnel." />
		<tag k="ref" v="127" />
		<tag k="source" v="cycletourer.co.uk" />
		<tag k="tunnel:name" v="Alnestunnelen" />
	</node>
</osm>
"""

class TestMatch(unittest.TestCase):
    def setUp(self):
        pass

    def parse_xml(self, xml):
        osm = osmapis.OSM.from_xml(xml.strip())
        return osm
    
    def test_Alnestunnelen(self):
        vegvesen = self.parse_xml(Alnestunnelen_vegvesen)
        cycletourer = self.parse_xml(Alnestunnelen_cycletourer)
        match_lists, unmatched_list = tunnels_webpage.match(vegvesen, cycletourer)

        print 'matched', match_lists
        for key, row in match_lists.iteritems():
            for item in row:
                print 'item in matched', item
        
        print 'unmatched', unmatched_list
        for item in unmatched_list:
            print 'item in unmatched', item
        
        self.assertEqual(len(match_lists), 1)
        self.assertEqual(len(unmatched_list), 1)
        expected_key = 'Alnestunnelen 127'
        self.assertTrue(expected_key in match_lists, msg='expected key = %s, got keys = %s' % ('Alnestunnelen 127', match_lists.keys()))
        #assert False

    def test_Alnestunnelen_reverse(self):
        vegvesen = self.parse_xml(Alnestunnelen_vegvesen)
        cycletourer = self.parse_xml(Alnestunnelen_cycletourer)
        match_lists, unmatched_list = tunnels_webpage.match(cycletourer, vegvesen)

        print 'matched', match_lists
        for key, row in match_lists.iteritems():
            for item in row:
                print 'item in matched', item
        
        print 'unmatched', unmatched_list
        for item in unmatched_list:
            print 'item in unmatched', item
        
        self.assertEqual(len(match_lists), 1)
        self.assertEqual(len(unmatched_list), 1)
        expected_key = 'Alnestunnelen 127'
        self.assertTrue(expected_key in match_lists, msg='expected key = %s, got keys = %s' % ('Alnestunnelen 127', match_lists.keys()))
        
