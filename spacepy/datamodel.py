#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
The datamodel classes constitute a data model implementation
meant to mirror the functionality of the data model output from pycdf, though
implemented slightly differently.

This contains the following classes:
 * :py:class:`dmarray` - numpy arrays that support .attrs for information about the data
 * :py:class:`SpaceData` - base class that extends dict, to be extended by others
    Currently used in GPScode and other projects

Authors: Steve Morley and Brian Larsen

Additional Contributors: Charles Kiyanda and Miles Engel

Institution: Los Alamos National Laboratory

Contact: smorley@lanl.gov; balarsen@lanl.gov

Copyright ©2010 Los Alamos National Security, LLC.


About datamodel
---------------

The SpacePy datamodel module implements classes that are designed to make implementing a standard
data model easy. The concepts are very similar to those used in standards like HDF5, netCDF and
NASA CDF.

The basic container type is analogous to a folder (on a filesystem; HDF5 calls this a
group): Here we implement this as a dictionary-like object, a datamodel.SpaceData object, which
also carries attributes. These attributes can be considered to be global, i.e. relevant for the
entire folder. The next container type is for storing data and is based on a numpy array, this
class is datamodel.dmarray and also carries attributes. The dmarray class is analogous to an
HDF5 dataset.

In fact, HDF5 can be loaded directly into a SpacePy datamodel, carrying across all attributes,
using the function fromHDF5:

    >>> import spacepy.datamodel as dm
    >>> data = dm.fromHDF5('test.h5')


Examples
--------

Imagine representing some satellite data within the global attributes might be
the mission name and the instrument PI, the variables might be the
instrument counts [n-dimensional array], timestamps[1-dimensional array and an orbit number [scalar].
Each variable will have one attribute (for this example).

    >>> import spacepy.datamodel as dm
    >>> mydata = dm.SpaceData(attrs={'MissionName': 'BigSat1'})
    >>> mydata['Counts'] = dm.dmarray([[42, 69, 77], [100, 200, 250]], attrs={'Units': 'cnts/s'})
    >>> mydata['Epoch'] = dm.dmarray([1, 2, 3], attrs={'units': 'minutes'})
    >>> mydata['OrbitNumber'] = dm.dmarray(16, attrs={'StartsFrom': 1})
    >>> mydata.attrs['PI'] 'Prof. Big Shot'

This has now populated a structure that can map directly to a NASA CDF or a HDF5. To visualize our datamodel,
we can use the :py:func:`toolbox.dictree` function (which works for any dictionary-like object).

    >>> import spacepy.toolbox as tb
    >>> tb.dictree(mydata, attrs=True)
    +
    :|____MissionName
    :|____PI
    |____Counts
         :|____Units
    |____Epoch
         :|____units
    |____OrbitNumber
         :|____StartsFrom


Guide for NASA CDF users
------------------------
By definition, a NASA CDF only has a single `layer'. That is, a CDF contains a series of records
(stored variables of various types) and a set of attributes that are either global or local in
scope. Thus to use SpacePy's datamodel to capture the functionality of CDF the two basic data types
are all that is required, and the main constraint is that datamodel.SpaceData objects cannot be
nested (more on this later, if conversion from a nested datamodel to a flat datamodel is required).


Opening a CDF and working directly with the contents can be easily done using the PyCDF module, however,
if you wish to load the entire contents of a CDF directly into a datamodel (complete with attributes)
the following will make life easier:

    >>> import spacepy.datamodel as dm
    >>> data = dm.fromCDF('test.cdf')

"""

from __future__ import division
import numpy, copy, datetime, os, warnings
import re, json
from toolbox import dictree

__contact__ = 'Steve Morley, smorley@lanl.gov'

class DMWarning(Warning):
    """
    Warnings class for datamodel, subclassed so it can be set to always
    """
    pass
warnings.simplefilter('always', DMWarning)

class dmarray(numpy.ndarray):
    """
    Container for data within a SpaceData object

    Examples
    --------
    >>> import spacepy.datamodel as datamodel
    >>> position = datamodel.dmarray([1,2,3], attrs={'coord_system':'GSM'})
    >>> position
    dmarray([1, 2, 3])
    >>> position.attrs
    {'coord_system': 'GSM'}a

    The dmarray, like a numpy ndarray, is versatile and can store
    any datatype; dmarrays are not just for arrays.

    >>> name = datamodel.dmarray('TestName')
    dmarray('TestName')

    To extract the string (or scalar quantity), use the tolist method

    >>> name.tolist()
    'TestName'

    Methods
    -------
    addAttribute : adds another attribute to the allowed list

    Raises
    ------
    NameError
        raised is the request name was not added to the allowed attributes list


    """
    Allowed_Attributes = ['attrs']

    def __new__(cls, input_array, attrs=None):
       # Input array is an already formed ndarray instance
       # We first cast to be our class type
       obj = numpy.asarray(input_array).view(cls)
       # add the new attribute to the created instance
       if attrs != None:
           obj.attrs = attrs
       else:
           obj.attrs = {}
       # Finally, return the newly created object:
       return obj

    def __array_finalize__(self, obj):
       # see InfoArray.__array_finalize__ for comments
        if obj is None:
            return
        for val in self.Allowed_Attributes:
            self.__setattr__(val, getattr(obj, val, {}))

    def __reduce__(self):
        """This is called when pickling, see:
        http://www.mail-archive.com/numpy-discussion@scipy.org/msg02446.html
        for this particular example.
        Only the attributes in Allowed_Attributes can exist
        """
        object_state = list(numpy.ndarray.__reduce__(self))
        subclass_state = tuple([tuple([val, self.__getattribute__(val)]) for val in self.Allowed_Attributes])
        object_state[2] = (object_state[2],subclass_state)
        return tuple(object_state)

    def __setstate__(self, state):
        """Used for unpickling after __reduce__ the self.attrs is recovered from
        the way it was saved and reset.
        """
        nd_state, own_state = state
        numpy.ndarray.__setstate__(self,nd_state)
        for i, val in enumerate(own_state):
            if not val[0] in self.Allowed_Attributes: # this is attrs
                self.Allowed_Attributes.append(own_state[i][0])
            self.__setattr__(own_state[i][0], own_state[i][1])

    def __setattr__(self, name, value):
        """Make sure that .attrs is the only attribute that we are allowing
        dmarray_ne took 15.324803 s
        dmarray_eq took 15.665865 s
        dmarray_assert took 16.025478 s
        It looks like != is the fastest, but not by much over 10000000 __setattr__
        """
        if name == 'Allowed_Attributes':
            pass
        elif not name in self.Allowed_Attributes:
            raise(TypeError("Only attribute listed in Allowed_Attributes can be set"))
        super(dmarray, self).__setattr__(name, value)

    def addAttribute(self, name, value=None):
        """Method to add an attribute to a dmarray
        equivalent to
        a = datamodel.dmarray([1,2,3])
        a.Allowed_Attributes = a.Allowed_Attributes + ['blabla']
        """
        if name in self.Allowed_Attributes:
            raise(NameError('{0} is already an attribute cannot add again'.format(name)))
        self.Allowed_Attributes.append(name)
        self.__setattr__(name, value)


class SpaceData(dict):
    """
    Datamodel class extending dict

    Methods
    -------
    flatten

    tree

    """

    def __init__(self, *args, **kwargs):
        """
        Base class for "Data Model" representation data

        Abstract method, reimplement

        Attributes
        ----------
        attrs : dict
            dictionary of the attributes of the SpaceData object

        """
        #raise(ValueError("Abstract method called, reimplement __init__"))
        self.attrs = {}
        if 'attrs' in kwargs:
            if hasattr(kwargs['attrs'], '__getitem__'):
                self.attrs = kwargs['attrs']
            del kwargs['attrs']

        super(SpaceData, self).__init__(*args, **kwargs)

    def tree(self, **kwargs):
        '''Print the contents of the SpaceData object in a visual tree

        Examples
        --------
        >>> import spacepy.datamodel as dm
        >>> import spacepy.toolbox as tb
        >>> a = dm.SpaceData()
        >>> a['1'] = dm.SpaceData(dog = 5)
        >>> a['4'] = dm.SpaceData(cat = 'kitty')
        >>> a['5'] = 4
        >>> a.tree()
        +
        |____1
             |____dog
        |____4
             |____cat
        |____5
        '''
        dictree(self, **kwargs)
    
    def flatten(self):
        '''
        Method to collapse datamodel to one level deep

        Examples
        --------
        >>> import spacepy.datamodel as dm
        >>> import spacepy.toolbox as tb
        >>> a = dm.SpaceData()
        >>> a['1'] = dm.SpaceData(dog = 5, pig = dm.SpaceData(fish=dm.SpaceData(a='carp', b='perch')))
        >>> a['4'] = dm.SpaceData(cat = 'kitty')
        >>> a['5'] = 4
        >>> tb.dictree(a)
        +
        |____1
             |____dog
             |____pig
                  |____fish
                       |____a
                       |____b
        |____4
             |____cat
        |____5

        >>> b = dm.flatten(a)
        >>> tb.dictree(b)
        +
        |____1<--dog
        |____1<--pig<--fish<--a
        |____1<--pig<--fish<--b
        |____4<--cat
        |____5

        >>> a.flatten()
        >>> tb.dictree(a)
        +
        |____1<--dog
        |____1<--pig<--fish<--a
        |____1<--pig<--fish<--b
        |____4<--cat
        |____5

        '''


        flatobj = flatten(self)
        remkeys = [key for key in self]
        for key in remkeys:
            del self[key]
        for key in flatobj:
            self[key] = copy.copy(flatobj[key])


def convertKeysToStr(SDobject):
    if isinstance(SDobject, SpaceData):
        newSDobject = SpaceData()
        newSDobject.attrs = SDobject.attrs
    else:
        newSDobject = {}
    for key in SDobject:
        if not isinstance(key, str):
            if isinstance(SDobject[key], dict):
                newSDobject[str(key)] = convertKeysToStr(SDobject[key])
            else:
                newSDobject[str(key)] = SDobject[key]
        else:
            if isinstance(SDobject[key], dict):
                newSDobject[key] = convertKeysToStr(SDobject[key])
            else:
                newSDobject[key] = SDobject[key]

    return newSDobject


def flatten(dobj):
    '''Function to collapse datamodel to one level deep

    Examples
    --------

    >>> import spacepy.datamodel as dm
    >>> import spacepy.toolbox as tb
    >>> a = dm.SpaceData()
    >>> a['1'] = dm.SpaceData(dog = 5, pig = dm.SpaceData(fish=dm.SpaceData(a='carp', b='perch')))
    >>> a['4'] = dm.SpaceData(cat = 'kitty')
    >>> a['5'] = 4
    >>> tb.dictree(a)
    +
    |____1
         |____dog
         |____pig
              |____fish
                   |____a
                   |____b
    |____4
         |____cat
    |____5

    >>> b = dm.flatten(a)
    >>> tb.dictree(b)
    +
    |____1<--dog
    |____1<--pig<--fish<--a
    |____1<--pig<--fish<--b
    |____4<--cat
    |____5

    >>> a.flatten()
    >>> tb.dictree(a)
    +
    |____1<--dog
    |____1<--pig<--fish<--a
    |____1<--pig<--fish<--b
    |____4<--cat
    |____5


    See Also
    --------
    SpaceData.flatten

    '''

    try:
        addme = dobj.__class__()
    except (TypeError):
        addme = SpaceData()
    remlist = []
    for key in dobj: #iterate over keys in SpaceData
        if isinstance(dobj[key], dict):
            remlist.append(key)
            newname = str(key) + '<--'
            for levkey in dobj[key]:
                if hasattr(dobj[key][levkey], 'keys'):
                    retdict = flatten(dobj[key][levkey])
                    for key2 in retdict:
                        addme[newname+levkey+'<--'+key2] = retdict[key2]
                else:
                    addme[newname+levkey] = copy.copy(dobj[key][levkey])
        else:
            addme[key] = copy.copy(dobj[key])
    return addme

def fromCDF(fname, **kwargs):
    '''
    Create a SpacePy datamodel representation of a NASA CDF file

    Parameters
    ----------
    file : string
        the name of the cdf file to be loaded into a datamodel

    Returns
    -------
    out : spacepy.datamodel.SpaceData
        SpaceData with associated attributes and variables in dmarrays

    Examples
    --------
    >>> import spacepy.datamodel as dm
    >>> data = dm.fromCDF('test.cdf')
    '''
    #TODO: add unflatten keyword and restore flattened variables
    try:
        from spacepy import pycdf
    except ImportError:
        raise ImportError("CDF converter requires NASA CDF library and SpacePy's pyCDF")

    try:
        cdfdata = pycdf.CDF(fname)
    except:
        raise IOError('Could not open %s' % fname)
    #make SpaceData and grab global attributes from CDF
    data = SpaceData()
    for akey in cdfdata.attrs:
        try:
            data.attrs[akey] = cdfdata.attrs[akey][:]
        except TypeError:
            #required for datetime objects, floats, etc.
            data.attrs[akey] = cdfdata.attrs[akey]

    #iterate on CDF variables and copy into dmarrays, carrying attrs
    for key in cdfdata:
        data[key] = dmarray(cdfdata[key][...])
        for akey in cdfdata[key].attrs:
            try:
                data[key].attrs[akey] = cdfdata[key].attrs[akey][:]
            except TypeError:
                data[key].attrs[akey] = cdfdata[key].attrs[akey]
    return data

def fromHDF5(fname, **kwargs):
    '''
    Create a SpacePy datamodel representation of an HDF5 file

    Parameters
    ----------
    file : string
        the name of the HDF5 file to be loaded into a datamodel

    Returns
    -------
    out : spacepy.datamodel.SpaceData
        SpaceData with associated attributes and variables in dmarrays

    Examples
    --------
    >>> import spacepy.datamodel as dm
    >>> data = dm.fromHDF5('test.hdf')

    Notes
    -----
    Known issues -- zero-sized datasets will break in h5py
    This is kluged by returning a dmarray containing a None
    '''
    def hdfcarryattrs(SDobject, hfile, path):
        if hasattr(hfile[path],'attrs'):
            for key, value in hfile[path].attrs.iteritems():
                try:
                    SDobject.attrs[key] = value
                except:
                    warnings.warn('The following key:value pair is not permitted\n' + 
                                    'key = {0} ({1})\n'.format(key, type(key)) + 
                                    'value = {0} ({1})'.format(value, type(value)), DMWarning)

    try:
        import h5py as hdf
    except ImportError:
        raise ImportError('HDF5 converter requires h5py')

    if type(fname) == str:
        hfile = hdf.File(fname, mode='r')
    else:
        hfile = fname
        #should test here for HDF file object

    if 'path' not in kwargs:
        path = '/'
    else:
        path = kwargs['path']

    SDobject = SpaceData()
    allowed_elems = [hdf.Group, hdf.Dataset]
    ##carry over the attributes
    hdfcarryattrs(SDobject, hfile, path)
    ##carry over the groups and datasets
    for key, value in hfile[path].iteritems():
        try:
            if type(value) is allowed_elems[0]: #if a group
                SDobject[key] = SpaceData()
                SDobject[key] = fromHDF5(hfile, path=path+'/'+key)
            elif type(value) is allowed_elems[1]: #if a dataset
                if len(value) != 0:
                    SDobject[key] = dmarray(value)
                else:
                    SDobject[key] = dmarray(None)
                hdfcarryattrs(SDobject[key], hfile, path+'/'+key)
        except:
            raise ValueError('HDF5 file contains type other than Group or Dataset')
    if path=='/': hfile.close()
    return SDobject

def toHDF5(fname, SDobject, **kwargs):
    '''
    Create an HDF5 file from a SpacePy datamodel representation

    Parameters
    ----------
    fname : str
        Filename to write to

    SDobject : spacepy.datamodel.SpaceData
        SpaceData with associated attributes and variables in dmarrays

    Other Parameters
    ----------------
    overwrite : bool (optional)
        allow overwrite of an existing target file (default True)
    mode : str (optional)
        HDF5 file open mode (a, w, r) (default 'a')

    Returns
    -------
    None
    '''
    def SDcarryattrs(SDobject, hfile, path, allowed_attrs):
        if hasattr(SDobject, 'attrs'):
            for key, value in SDobject.attrs.iteritems():
                if type(value) in allowed_attrs:
                    #test for datetimes in interables
                    if hasattr(value, '__iter__'):
                        value = [b.isoformat() for b in value if isinstance(b, datetime.datetime)]
                    if value or value is 0:
                        hfile[path].attrs[key] = value
                    else:
                        hfile[path].attrs[key] = ''
                else:
                    #TODO: add support for datetime in attrs (convert to isoformat)
                    warnings.warn('The following key:value pair is not permitted\n' + 
                                    'key = {0} ({1})\n'.format(key, type(key)) + 
                                    'value type {0} is not in the allowed attribute list'.format(type(value)), 
                                        DMWarning)

    try:
        import h5py as hdf
    except ImportError:
        raise ImportError('h5py is required to use HDF5 files')

    #mash these into a defaults dict...
    if 'mode' not in kwargs:
        wr_mo = 'a'
    else:
        wr_mo = kwargs['mode']

    if 'overwrite' not in kwargs: kwargs['overwrite'] = True
    if type(fname) == str:
        if os.path.isfile(fname) and not kwargs['overwrite']:
            raise(IOError('Cannot write HDF5, file exists (see overwrite)'))
        if os.path.isfile(fname) and kwargs['overwrite']:
            os.remove(fname)
        hfile = hdf.File(fname, mode=wr_mo)
    else:
        hfile = fname
        #should test here for HDF file object

    if 'path' in kwargs:
        path = kwargs['path']
    else:
        path = '/'

    allowed_attrs = [int, long, float, str, numpy.ndarray, list, tuple]
    allowed_elems = [SpaceData, dmarray]

    #first convert non-string keys to str
    SDobject = convertKeysToStr(SDobject)

    SDcarryattrs(SDobject,hfile,path,allowed_attrs)
    for key, value in SDobject.iteritems():
        if type(value) is allowed_elems[0]:
            hfile[path].create_group(key)
            toHDF5(hfile, SDobject[key], path=path+'/'+key)
        elif type(value) is allowed_elems[1]:
            try:
                hfile[path].create_dataset(key, data=value)
            except:
                if isinstance(value[0], datetime.datetime):
                    for i, val in enumerate(value): value[i] = val.isoformat()
                hfile[path].create_dataset(key, data=value.astype('|S35'))
                #else:
                #    hfile[path].create_dataset(key, data=value.astype(float))
            SDcarryattrs(SDobject[key], hfile, path+'/'+key, allowed_attrs)
        else:
            warnings.warn('The following data is not being written as is not of an allowed type\n' +
                           'key = {0} ({1})\n'.format(key, type(key)) + 
                              'value type {0} is not in the allowed data type list'.format(type(value)), 
                                  DMWarning)
    if path=='/': hfile.close()

def readJSONMetadata(fname, **kwargs):
    '''Read JSON metadata from an ASCII data file

    Parameters
    ----------
    fname : str
        Filename to read metadata from

    Other Parameters
    ----------------
    verbose : bool (optional)
        set verbose output so metadata tree prints on read (default False)

    Returns
    -------
    mdata: spacepy.datamodel.SpaceData
        SpaceData with the metadata from the file
    '''
    with open(fname, 'r') as f:
        lines = f.read()

    # isolate header
    p_srch = re.compile(r"^#(.*)$", re.M)
    hreg = re.findall(p_srch, lines)
    header = "".join(hreg)

    # isolate JSON field
    srch = re.search( r'\{\s*(.*)\s*\}', header )
    if isinstance(srch, type(None)):
        raise IOError('The input file has no valid JSON header. Must be valid JSON bounded by braces "{ }".')
    js = srch.group(1)
    inx = js.rfind('end JSON')
    
    if inx == -1:
        js = ' '.join(('{', js, '}'))
        mdatadict = json.loads(js)
    else:
        js = ' '.join(('{', js[:inx]))
        mdatadict = json.loads(js)

    mdata = SpaceData()
    for key in mdatadict:
       if 'START_COLUMN' in mdatadict[key]:
           mdata[key] = SpaceData(attrs=mdatadict[key])
       elif 'VALUES' in mdatadict[key]:
           dum = mdatadict[key].pop('VALUES')
           mdata[key] = dmarray(dum, attrs=mdatadict[key])
       else:
           mdata.attrs[key] = mdatadict[key]

    if 'verbose' in kwargs:
        if kwargs['verbose']:
            #pretty-print config_dict
            config_dict.tree(verbose=True, attrs=True)

    return mdata

