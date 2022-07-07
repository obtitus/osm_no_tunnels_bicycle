def remove_empty_values(dct):
    """Remove all dictionary items where the value is '' or None."""
    for key in list(dct.keys()):
        if dct[key] in ('', None):
            del dct[key]

def is_name_tag(key):
    """Returns true if 'key' looks like a name tag
    >>> is_name_tag('name')
    True
    >>> is_name_tag('tunnel:name')
    True
    >>> is_name_tag('alt_name')
    True
    >>> is_name_tag('int_name')
    True
    >>> is_name_tag('name:no')
    True
    >>> is_name_tag('old_name')
    True
    >>> is_name_tag('railway:name')
    False
    """
    
    if key == 'railway:name':
        return False
    # should cover name, alt_name, name:no, tunnel:name and possibly some false positives
    elif key.startswith('name') or key.endswith('name'):
        return True
    else:
        return False
                
