import collections

def merge_equal(osmobj, merge_list):
    '''
    Copied from depricated repo https://github.com/osmno/elveg2osm/blob/master/elveg2osm.py to ease dependency
    '''
    if len(merge_list) <= 1:
        # There is nothing to merge
        return
    
    # Remove nvdb-tags
    for way_id in merge_list:
        way = osmobj.ways[way_id]
        way.tags.pop('nvdb:id', None)
        way.tags.pop('nvdb:date', None)
        way.tags.pop('nvdb:id:part', None)

    # Split the ways in merge_list into subsets with identical tags
    eq_tags_dict = collections.defaultdict(list)
    for way_id in merge_list:
        frozen_tags = frozenset(osmobj.ways[way_id].tags.items())
        eq_tags_dict[frozen_tags].append(way_id)

    # Loop through the subsets with equal tags
    for merge_sublist in eq_tags_dict.values():
        # Index based on start-nodes and end nodes
        ways_from_start_node = collections.defaultdict(list)
        ways_from_end_node = collections.defaultdict(list)
        for way_id in merge_sublist:
            way = osmobj.ways[way_id]
            ways_from_start_node[way.nds[0]].append(way_id)
            ways_from_end_node[way.nds[-1]].append(way_id)

        # Start merging ways where start/end meet
        merge_subset = set(merge_sublist)
        # DEBUG
        #print "Starting merge_sublist " + str(merge_sublist)
        while len(merge_subset) > 0:
            new_way_string = collections.deque([merge_subset.pop()])
            # Add backwards
            first_node = osmobj.ways[new_way_string[0]].nds[0]
            while (first_node in ways_from_end_node and
                   len(ways_from_end_node[first_node]) == 1 and
                   ways_from_end_node[first_node][0] in merge_subset):
                new_way_string.extendleft(ways_from_end_node[first_node])
                merge_subset.remove(ways_from_end_node[first_node][0])
                first_node = osmobj.ways[new_way_string[0]].nds[0]
            # Add forwards
            last_node = osmobj.ways[new_way_string[-1]].nds[-1]
            while (last_node in ways_from_start_node and
                   len(ways_from_start_node[last_node]) == 1 and
                   ways_from_start_node[last_node][0] in merge_subset):
                new_way_string.extend(ways_from_start_node[last_node])
                merge_subset.remove(ways_from_start_node[last_node][0])
                last_node = osmobj.ways[new_way_string[-1]].nds[-1]
            # new_way_string is ready built, so convert it back to a list
            # (since deque cannot be sliced)
            new_way_string = list(new_way_string)
            # DEBUG
            #print "  Merge string" + str(new_way_string)
            # Generate node-string for merged way based on way_ids in new_way_string
            first_way = osmobj.ways[new_way_string[0]]
            for way_id in new_way_string[1:]:
                way = osmobj.ways[way_id]
                first_length = len(first_way.nds)
                way_length = len(way.nds)
                if first_length + way_length - 1 <= 2000:
                    first_way.nds.extend(way.nds[1:])
                    osmobj.discard(way)
                else:
                    first_way = way
