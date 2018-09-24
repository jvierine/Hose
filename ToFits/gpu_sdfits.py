#!/usr/bin/env python2

#------------------------------------------------------------------------
__doc__="""\
gpu_sdfits - conversion of GPU spectrograph spectra and metadata into
          SDFITS style FITS files. The aim is to be run directly from
          the command line with little or no information beyond the
          pointer to the directory tree with the GPU spectrometer
          data. 

 Uses: gpu_read.py

 Assume:
  Each subdirectory has a set of spectra and noise files and one metadata
  file to go with it. The aim will be to encapsulate all the spectra and
  noise files into one fits file, merging in the metadata.

 - within each subdirectory:
  = check for existing fits file for the subdirectory
  = list files
  = read in the metadata file first
   * construct needed metadata based FITS header information
   * construct needed lookup tables
  = loop over input spectra and noise files - sorted in time order

 Debugging tip: 
 - Dump output binary tables using futils_tablist to check that the 
   columns are in fact what you think they are
 - or check structure with fitsinfo (from the HEASARC fits package)

 Table columns will have to be built up row by row, so append to each
 column as each spectrum and its associated metadata are read and
 parsed.

 Structure:
  - primary HDU
  - spectrum binary table (named MATRIX)
  - noise binary table (named NOISE)
 For storage and binary table structure efficiency and simplicity, it makes
 sense to construct separate binary tables because the table structures are
 slightly different because the data formats differ.

 Operational order:
  1) construct list of directory(ies) and the files there-in.
  2) Test for existing FITS file that would be auto-constructed from
    the directory. If found, go to next directory. If override, then
    reconstruct anyway.
  3) read in meta-data.json file for the directory (assuming there is
    only 1).
  4) loop over spectrum files:
    (a) construct metadata at time of spectrum
    (b) add metadata to the column lists
    (c) add spectrum to the data matrix list
    (d) sort based on datetime to ensure they are in time order
  5) loop over noise power files:
    (a) construct metadata at time of noise reading
    (b) add metadata to the column lists
    (c) add noise power info to the data matrix list
    (d) sort based on datetime to ensure they are in time order
  6) Construct FITS - primary HDU, spectrum binary table HDU, noise 
    binary table HDU.
"""
__usage__="""
 Usage: ./gpu_sdfits.py Directory

 If directory contains wildcards, then you should quote it to avoid
 expansion by the shell. So, for example:
    sh> ./gpu_sdfits.py ../Data/scan[12]
 will do ../Data/scan1
    sh> ./gpu_sdfits.py '../Data/scan[12]'
 will do ../Data/scan1 and ../Data/scan2
"""
__author__="S. Levine"
__date__="2018 Sep 23"

#------------------------------------------------------------------------
# import the FITS io routines for the I/O
from astropy.io import fits

# import astropy coordinates routines
from astropy.coordinates import EarthLocation, SkyCoord, AltAz, ICRS, Galactic
from astropy.time        import Time
import astropy.units     as u

# JSON reading routines
import json

# import numpy for its array handling
import numpy as np

# time/date routines
from time import gmtime, strftime
import datetime as dt

# system path operations
import os

# GPU file reading and parsing classes/routines
import gpu_read as r

# random was used for some testing. can be removed.
import random

# data structure for global metadata
site_meta  = {'origin' : None}
wthr_meta  = {'temp'   : None}
coord_meta = {'alt'    : None}
wcs_meta   = {'maxis'  : None}

# Spectrum dictionary - it is structured as a dictionary of lists for
#  compatibility with the FITS binary table column construction.
obs_spec = {'datetime': [], 'date-obs': [], 'ut': [], 'object': [],
            'obstime': [], 'experiment': [], 'scan': [], 'navg': [],
            'spec_len': [], 'spec_data_type': [], 'spec': [],
            'az': [], 'el':[]}

# Noise dictionary
obs_nois   = {'datetime': [], 'date-obs': [], 'ut': [], 'object': [],
              'obstime': [], 'experiment': [], 'scan': [],
              'accum_len': [], 'switch_freq': [], 'blanking_per': [],
              'noise': [], 'az': [], 'el':[]}

#------------------------------------------------------------------------
# Functions

def sort_dict_of_lists (input_dict, srtkey):
    """\
    Given a dictionary with a set of lists, sort all the
    lists based on one of the lists. Return a dict with
    the sorted lists.
    """
    
    # To be used to ensure that each array in input_dict is in
    # increasing primary key sort order. Set up separate list of
    # primary sort key then zip together all the other obs_spec lists
    # after the sort index. Sort and then copy into the return
    # dictionary.

    j = sorted (input_dict.keys())
    tmp_sort_arr = input_dict[srtkey]
    tmppack = zip(tmp_sort_arr, *(input_dict[k] for k in j))
    srtpack = map(list, zip(*sorted(tmppack)))
    sidx = 1
    ret_dict = {}
    for k in j:
        ret_dict[k] = srtpack[sidx]
        sidx += 1

    return ret_dict

def sdf_getobs_spec (spec_record, meta_info):
    """
    Populate observation specific meta-data and spectrum for input record.
    The expected record is a GPUSpec spectrum object.
    """
    global obs_spec

    # start with UT date/time as date-obs in isoformat
    lut = spec_record.start_ut()
    obs_spec['datetime'].append(lut)
    obs_spec['date-obs'].append(lut.isoformat())
    obs_spec['ut'].append(sexig2decim (lut.time()))
    
    obs_spec['object'].append(spec_record.source_name())
    obs_spec['obstime'].append(spec_record.obstime())
    obs_spec['experiment'].append(spec_record.experiment_name())
    obs_spec['scan'].append(spec_record.scan_name())
    obs_spec['navg'].append(spec_record.n_averages())
    obs_spec['spec_len'].append(spec_record.spectrum_length())
    obs_spec['spec_data_type'].append(spec_record.spectrum_data_type_size())
    
    obs_spec['spec'].append(spec_record.spectrum())

    if (meta_info != None):
        a = meta_info.antenna_pos_at_time(lut)
        obs_spec['az'].append(a['fields']['az'])
        obs_spec['el'].append(a['fields']['el'])
    else:
        obs_spec['az'].append(-1.0)
        obs_spec['el'].append(-1.0)

    #print ('{} {}'.format(obs_spec['date-obs'], obs_spec['ut']))

    return

def sdf_getobs_nois (nois_record, meta_info):
    """
    Populate observation specific meta-data and noise data for input record.
    The expected record is a GPUNoise object.
    """
    global obs_nois

    # start with UT date/time as date-obs in isoformat
    lut = nois_record.start_ut()
    obs_nois['datetime'].append(lut)
    obs_nois['date-obs'].append(lut.isoformat())
    obs_nois['ut'].append(sexig2decim (lut.time()))
    
    obs_nois['object'].append(nois_record.source_name())
    obs_nois['obstime'].append(nois_record.obstime())
    obs_nois['experiment'].append(nois_record.experiment_name())
    obs_nois['scan'].append(nois_record.scan_name())

    obs_nois['accum_len'].append(nois_record.accumulation_length())
    obs_nois['switch_freq'].append(nois_record.switching_frequency())
    obs_nois['blanking_per'].append(nois_record.blanking_period())

    obs_nois['noise'].append(nois_record.noise())
    
    if (meta_info != None):
        a = meta_info.antenna_pos_at_time(lut)
        obs_nois['az'].append(a['fields']['az'])
        obs_nois['el'].append(a['fields']['el'])
    else:
        obs_nois['az'].append(-1.0)
        obs_nois['el'].append(-1.0)

    #print ('{} {}'.format(obs_nois['date-obs'], obs_nois['ut']))

    return

def sdf_getsite (origin=None, site=None, telescope=None, instrument=None):
    """
    Populate site metadata structure
    site is a triple {lat, lon, alt}
    telescope and instrument are the respective names.
    """
    global site_meta

    # default to Haystack 37-m (for now)
    site_meta = { 'origin': 'Haystack Observatory',
                  'site': {'lat'  : +42.62333333,
                           'lon'  : -71.48833333,
                           'elev' : 131 },
                  'telescope'  : '37-meter',
                  'instrument' : 'GPU spectrometer',
                  'beameff'    : 1.0,
                  'forweff'    : 1.0}

    if (origin != None):
        site_meta['origin'] = origin

    if (site != None):
        site_meta['site'] = site

    if (telescope != None):
        site_meta['telescope'] = telescope

    if (instrument != None):
        site_meta['instrument'] = instrument

    return

def sdf_getwthr (dewpoint=None,    humidity=None, pressure=None,
                 temperature=None, winddir=None,  windspeed=None,
                 tau=None):
    """
    Populate weather metadata structure
    Default values (from SLALIB refraction code):
      tdk = 273.15 Default temperature (K)
      pmb = 1013.25 Default pressure (mBars == hPa)
      rh  = 0.5 Default relative humidity (0.0 - 1.0)
      tlr = 0.0065 Default Tropospheric lapse rate (K/meter)
    """
    global wthr_meta

    # defaults
    wthr_meta = { 'dewpoint'  : 273.15,
                  'humidity'  : 0.5,
                  'pressure'  : 1013.25,
                  'toutside'  : 293.15,
                  'winddir'   : 0.0,
                  'windspeed' : 0.0,
                  'tau-atm'   : 0.0 }

    if (dewpoint != None):
        wthr_meta['dewpoint'] = dewpoint

    if (humidity != None):
        wthr_meta['humidity'] = humidity

    if (pressure != None):
        wthr_meta['pressure'] = pressure

    if (temperature != None):
        wthr_meta['toutside'] = temperature

    if (winddir != None):
        wthr_meta['winddir'] = winddir

    if (windspeed != None):
        wthr_meta['windspeed'] = windspeed

    if (tau != None):
        wthr_meta['tau-atm'] = tau

    return

def sdf_getwcs (maxis=None, maxisN=None, ctypeN=None, crvalN=None,
                crpixN=None, cdeltN=None):
    """
    Populate default WCS column header info
    """
    global wcs_meta

    # defaults
    if (maxis == None):
        wcs_meta['maxis']  = 4
        wcs_meta['maxisN'] = [1]*4
        wcs_meta['ctypeN'] = ['FREQ', 'RA', 'DEC', 'STOKES']
        wcs_meta['crvalN'] = [0.0]*4
        wcs_meta['crpixN'] = [0.0]*4
        wcs_meta['cdeltN'] = [0.0]*4
    else:
        wcs_meta['maxis']  = maxis
        wcs_meta['maxisN'] = maxisN
        wcs_meta['ctypeN'] = ctypeN
        wcs_meta['crvalN'] = crvalN
        wcs_meta['crpixN'] = crpixN
        wcs_meta['cdeltN'] = cdeltN

    return

def altaz2radec (alt, az, obstime, site, wthr=None):
    """
    From Alt, Az, UT, Location compute
    RA, Dec, galactic l,b and lst
    Accepts either single values, or lists (ie alt = [a1, a2, .., aN]
    and returns corresponding type.
    """

    osi = EarthLocation(lat=site['lat']*u.deg,
                        lon=site['lon']*u.deg,
                        height=site['elev']*u.m)

    oti = Time(obstime, scale='utc', location=osi)

    lst = oti.sidereal_time('mean').to_string(sep='')

    azel = SkyCoord(alt=alt*u.deg, az=az*u.deg, frame='altaz', obstime=oti,
                    location=osi, pressure=0)

    eqc = azel.transform_to('icrs')
    glc = azel.transform_to('galactic')

    return eqc, glc, lst

def sexig2decim (sxtim):
    """
    convert datetime time portion in sexigesimal to decimal seconds.
    ie: input sxtim == dattim.time() element
    """
    h = sxtim.hour
    m = sxtim.minute
    s = sxtim.second
    f = sxtim.microsecond
    d = ((h * 60.0) + m) * 60.0 + s + f/1000000.

    return d

#------------------------------------------------------------------------
# FITS file construction functions

def sdf_primary_hdu (object=None, telescope=None, instrument=None):
    """
    Construct SD FITS file primary HDU. Since most stuff will be
    in the binary table HDU, this is pretty generic, with just a few
    added items.
    Additions for SDFITS came from:
      Liszt, H. S. 1995, A FITS Binary Table Convention for Interchange
      of Single Dish Data in Radio Astronomy.

    """
    global site_meta

    # load site meta-data if not yet done
    if (site_meta['origin'] == None):
        sdf_getmeta(telescope=telescope, instrument=instrument)
    else:
        if (telescope != None):
            site_meta['telescope'] = telescope

        if (instrument != None):
            site_meta['instrument'] = instrument


    # prep the primary HDU header
    hdr = fits.Header()
    hdr['ORIGIN'] = site_meta['origin']
    hdr['DATE'] = (strftime("%Y-%m-%dT%H:%M:%S", gmtime()))

    if (object != None):
        hdr['OBJECT'] = object
    else:
        hdr['OBJECT'] = 'OBJECTID'

    hdr['TELESCOP'] = site_meta['telescope']
    hdr['INSTRUME'] = site_meta['instrument']

    # How to put in a comment?

    primary_hdu = fits.PrimaryHDU(header=hdr)

    return primary_hdu

def sdf_bintab_hdr (obsrec, extname='MATRIX', obsmode=None):
    """
    setup common binary table header information
    will return dictionary a, and fits header hdr.
    """
    
    # set up null dictionary for local arrays
    a = {}

    # conversion of alt,az, date/time vectors to ra,dec & l,b & lst
    aeq, agal, alst = altaz2radec (obsrec['el'], obsrec['az'], 
                                   obsrec['date-obs'], 
                                   site_meta['site'])
    a['equinox'] = [2000.0] * 3
    a['ra']   = aeq.ra.deg
    a['dec']  = aeq.dec.deg
    a['glon'] = agal.l.deg
    a['glat'] = agal.b.deg
    a['lst']  = alst

    # Compute the offset in Xi, Eta from the first pointing
    #  Need to make sure the SkyCoord frames for all the Ra,Dec points
    #  are the same. This copy removes the obstime vector, which was
    #  causing trouble.
    zrd = SkyCoord (ra=a['ra'][0]*u.deg, dec=a['dec'][0]*u.deg, frame='icrs')
    ord = SkyCoord (ra=a['ra']*u.deg,    dec=a['dec']*u.deg,    frame='icrs')
    dra, ddec = zrd.spherical_offsets_to(ord)
    a['cdelt2'] = dra
    a['cdelt3'] = ddec

    # add extra header keyword to BinTable HDU
    hdr = fits.Header()
    hdr['BZERO']    = 0.0
    hdr['BSCALE']   = 1.0

    # SINGLE DISH is what is called out in SDFITS def'n
    # hdr['EXTNAME']  = 'SINGLE DISH'
    # MATRIX is what is shown in CLASS samples/docs
    hdr['EXTNAME']  = extname

    # hdr['EXTLEVEL'] = 1   # optional, defaults to 1
    hdr['EXTVER']   = 1   # optional, defaults to 1
    hdr['NMATRIX']  = 1   # required, 1 data set per row

    # WCS Virtual column defaults
    # will get overridden by table columns with same ID
    hdr['MAXIS']  = wcs_meta['maxis']
    for i in range(wcs_meta['maxis']):
        j = i + 1
        hdr['MAXIS{}'.format(j)] = wcs_meta['maxisN'][i]
        hdr['CTYPE{}'.format(j)] = wcs_meta['ctypeN'][i]
        hdr['CDELT{}'.format(j)] = wcs_meta['cdeltN'][i]
        hdr['CRPIX{}'.format(j)] = wcs_meta['crpixN'][i]

        if   (wcs_meta['ctypeN'][i] == 'RA'):
            hdr['CRVAL{}'.format(j)] = a['ra'][0]
        elif (wcs_meta['ctypeN'][i] == 'DEC'):
            hdr['CRVAL{}'.format(j)] = a['dec'][0]
        else:
            hdr['CRVAL{}'.format(j)] = wcs_meta['crvalN'][i]

    # Site Metadata
    hdr['TELESCOP'] = site_meta['telescope']
    hdr['SITELONG'] = site_meta['site']['lon']
    hdr['SITELAT']  = site_meta['site']['lat']
    hdr['SITEELEV'] = site_meta['site']['elev']

    # freq & velocity default info
    hdr['FOFFSET']  = 0.0  # class hdr
    hdr['RESTFREQ'] = 1.0  # class hdr
    hdr['VELO-LSR'] = 0.0  # class hdr
    hdr['VELDEF']   = 'RADI-LSR'  # class hdr
    hdr['DELTAV']   = 0.0  # class hdr

    hdr['BEAMEFF']  = site_meta['beameff']
    hdr['FORWEFF']  = site_meta['forweff']
    
    # Presume equinox/epoch of coordinates is J2000/2000
    hdr['EPOCH'] = 2000.0

    # Environmental Metadata
    hdr['DEWPOINT'] = wthr_meta['dewpoint']
    hdr['HUMIDITY'] = wthr_meta['humidity']
    hdr['PRESSURE'] = wthr_meta['pressure']
    hdr['TAU-ATM']  = wthr_meta['tau-atm']
    hdr['TOUTSIDE'] = wthr_meta['toutside']
    hdr['WINDDIRE'] = wthr_meta['winddir']
    hdr['WINDSPEE'] = wthr_meta['windspeed']

    if ( obsmode != 'None'):
        # should limit options to {LINE,CONT,PULS} x 
        #                         {PSSW,FQSW,BMSW,PLSW,LDSW,TLPW}
        hdr['OBSMODE'] = obsmode


    return a, hdr

def sdf_spectable_hdu(obsmode=None, max1=0):
    """
    Construct a FITS binary table HDU for spectrum data in single dish
    (SDFITS) radio data format.

    Define Table Columns - set up data arrays, then define column
    specs then create ensemble of columns, and finally make a Binary
    Table HDU from the defined col set
    """

    # set up null dictionary for columns
    c = {}

    # set up null dictionary for local arrays
    a = {}

    a, hdr = sdf_bintab_hdr (obs_spec, extname='MATRIX', obsmode=obsmode)
    
    c['scan']     = fits.Column(name='SCAN',     format='256A',
                                array=obs_spec['scan'])

    c['object']   = fits.Column(name='OBJECT',   format='12A', 
                                array=obs_spec['object'])

    # Check for RA, Dec columns to pass into CRVALs in table
    for i in range(wcs_meta['maxis']):
        j = i + 1
        if   (wcs_meta['ctypeN'][i] == 'RA'):
            c['ra']   = fits.Column(name='CRVAL{}'.format(j),
                                         format='1E', unit='degrees',
                                         array=a['ra'])

        elif (wcs_meta['ctypeN'][i] == 'DEC'):
            c['dec']   = fits.Column(name='CRVAL{}'.format(j),
                                         format='1E', unit='degrees',
                                         array=a['dec'])

    # a['tsys'] = ?
    c['tsys']       = fits.Column(name='TSYS',     format='1E', unit='K')
    #                              array=a['tsys'])

    # a['imagfreq'] = ?
    c['imagfreq']   = fits.Column(name='IMAGFREQ', format='1E', unit='Hz')
    #                              array=a['restfreq'])

    # a['tau-atm'] = ?
    c['tau-atm']    = fits.Column(name='TAU-ATM', format='1E')
    #                              array=a['tau-atm'])

    # a['mh2o'] = ?
    c['mh2o']       = fits.Column(name='MH2O', format='1E')
    #                              array=a['mh2o'])

    # a['pressure'] = ?
    c['pressure']   = fits.Column(name='PRESSURE', format='1E', unit='hPa')
    #                              array=a['pressure'])

    # a['tchop'] = ?
    c['tchop']      = fits.Column(name='TCHOP',    format='1E', unit='K')
    #                              array=a['tchop'])

    c['el']        = fits.Column(name='ELEVATIO', format='1E', unit='degrees',
                                 array=obs_spec['el'])
    c['az']        = fits.Column(name='AZIMUTH',  format='1E', unit='degrees',
                                 array=obs_spec['az'])

    c['ut']        = fits.Column(name='UT',       format='1D', 
                                 array=obs_spec['ut'])
    # a['lst'] = ?
    c['lst']       = fits.Column(name='LST',      format='1D', 
                                 array=a['lst'])

    c['obstime']   = fits.Column(name='OBSTIME', format='1E', unit='seconds',
                                 array=obs_spec['obstime'])


    # Currently assumes that all spectra will be the same length
    #  and so uses the length of the first one to set the size
    if (max1 == 0):
        # dsize = '{}E'.format(wcs_meta['maxisN'][0])
        dsize = '{}E'.format(int(obs_spec['spec_len'][0]))
    else:
        dsize = '{}E'.format(max1)

    c['spec']     = fits.Column(name='SPECTRUM',  format=dsize, unit='power',
                                 array=obs_spec['spec'])


    cols = fits.ColDefs([c[i] for i in sorted(c.keys())])
    hdu  = fits.BinTableHDU.from_columns(cols, header=hdr)

    print ('{}'.format(hdu.columns))

    return hdu

def sdf_noistable_hdu(obsmode=None, max1=0):
    """
    Construct a FITS binary table HDU for noise data in single dish
    (SDFITS) radio data format.

    Define Table Columns - set up data arrays, then define column
    specs then create ensemble of columns, and finally make a Binary
    Table HDU from the defined col set
    """

    # set up null dictionary for columns
    c = {}

    # set up null dictionary for local arrays
    a = {}

    a, hdr = sdf_bintab_hdr (obs_nois, extname='NOISE', obsmode=obsmode)
    
    c['scan']     = fits.Column(name='SCAN',     format='256A',
                                array=obs_nois['scan'])

    c['object']   = fits.Column(name='OBJECT',   format='12A', 
                                array=obs_nois['object'])

    # Check for RA, Dec columns to pass into CRVALs in table
    for i in range(wcs_meta['maxis']):
        j = i + 1
        if   (wcs_meta['ctypeN'][i] == 'RA'):
            c['ra']   = fits.Column(name='CRVAL{}'.format(j),
                                         format='1E', unit='degrees',
                                         array=a['ra'])

        elif (wcs_meta['ctypeN'][i] == 'DEC'):
            c['dec']   = fits.Column(name='CRVAL{}'.format(j),
                                         format='1E', unit='degrees',
                                         array=a['dec'])

    # a['tsys'] = ?
    c['tsys']       = fits.Column(name='TSYS',     format='1E', unit='K')
    #                              array=a['tsys'])

    # a['imagfreq'] = ?
    c['imagfreq']   = fits.Column(name='IMAGFREQ', format='1E', unit='Hz')
    #                              array=a['restfreq'])

    # a['tau-atm'] = ?
    c['tau-atm']    = fits.Column(name='TAU-ATM', format='1E')
    #                              array=a['tau-atm'])

    # a['mh2o'] = ?
    c['mh2o']       = fits.Column(name='MH2O', format='1E')
    #                              array=a['mh2o'])

    # a['pressure'] = ?
    c['pressure']   = fits.Column(name='PRESSURE', format='1E', unit='hPa')
    #                              array=a['pressure'])

    # a['tchop'] = ?
    c['tchop']      = fits.Column(name='TCHOP',    format='1E', unit='K')
    #                              array=a['tchop'])

    c['el']        = fits.Column(name='ELEVATIO', format='1E', unit='degrees',
                                 array=obs_nois['el'])
    c['az']        = fits.Column(name='AZIMUTH',  format='1E', unit='degrees',
                                 array=obs_nois['az'])

    c['ut']        = fits.Column(name='UT',       format='1D', 
                                 array=obs_nois['ut'])
    # a['lst'] = ?
    c['lst']       = fits.Column(name='LST',      format='1D', 
                                 array=a['lst'])

    c['obstime']   = fits.Column(name='OBSTIME', format='1E', unit='seconds',
                                 array=obs_nois['obstime'])


    # TBD construct noise columns based on class defs from hose
    
    # Currently assumes that all spectra will be the same length
    #  and so uses the length of the first one to set the size
#    if (max1 == 0):
#        # dsize = '{}E'.format(wcs_meta['maxisN'][0])
#        dsize = '{}E'.format(int(obs_nois['spec_len'][0]))
#    else:
#        dsize = '{}E'.format(max1)
#
#    c['spec']     = fits.Column(name='SPECTRUM',  format=dsize, unit='power',
#                                 array=obs_spec['spec'])


    cols = fits.ColDefs([c[i] for i in sorted(c.keys())])
    hdu  = fits.BinTableHDU.from_columns(cols, header=hdr)

    print ('{}'.format(hdu.columns))

    return hdu

def sdf_mkfits (ofile=None, max1=0):
    """
    Construct full fits file
    """

    sdf_getsite()
    sdf_getwthr()
    sdf_getwcs(maxis=4, maxisN=[2,1,1,1], ctypeN=['FREQ', 'RA', 'DEC', 'STOKES'], 
               crvalN=[0]*4, crpixN=[2/2, 0, 0, 0], cdeltN=[1,0,0,0])
    
    # Loading the obs_spec and obs_nois dictionaries is done outside
    #  this.
    # sdf_getobs_spec()
    # sdf_getobs_nois()

    phdu = sdf_primary_hdu (telescope='Westford')
    shdu = sdf_spectable_hdu (obsmode='LINEPSSW', max1=max1)
    nhdu = sdf_noistable_hdu (obsmode='LINEPSSW', max1=max1)
    
    # include primary and table HDUs into one
    hdu1 = fits.HDUList([phdu, shdu, nhdu])

    # Write out FITS table file
    if (ofile != None):
        hdu1.writeto (ofile)

    return

#------------------------------------------------------------------------
# Upper level driver routines - handle directory listing/searching etc.
def loop_over_dirs (inputs):
    """
    Overall driver to load in spectra and noise data in all 
    directories in the list.
    [NOT YET IMPLEMENTED OPTION:
      maxperfits == max number of spectra per fits file. If < 0, do all.
    ]
    """
    
    # Expect argument to be directory with scans or scan directories
    # argone = sys.argv[1]
    argone = inputs
    print ('{}'.format(argone))

    # within each scan directory, construct lists of spec, noise and
    # metadata files
    d, fs, fn, fm, ff = r.construct_lists (argone)

    for n in range(len(d)):
        numspec = load_spectra (n, d[n], fs[n], fm[n], ff[n])
        numnois = load_noise   (n, d[n], fn[n], fm[n], ff[n])
        if ((numspec > 0) or (numnois > 0)):
            froot = os.path.basename(d[n])
            ofile = '{}/{}.fits'.format(d[n],froot)
            sdf_mkfits(ofile=ofile)
        
    # print ('{}'.format(obs_spec['ut']))
    
    return

def load_spectra(idnum, d, fs, fm, ff):
    """
    Overall driver to load in spectra in nth directory in the list
    idnum == n'th directory - currently not used
    d == dir path
    fs == list of spec files
    fm == list of meta files
    ff == list of fits files
    [NOT YET IMPLEMENTED OPTION:
      maxper == max number of spectra to insert in a fits file. If < 0, do all.
    ]
    """
    global obs_spec
    
    anyfits = len(ff)
        
    print ('Start {}'.format(dt.datetime.now().ctime()))
    print ('Dir: {}'.format(d))
    print ('  Spec files: {}'.format(len(fs)))
    print ('  Metadata file(s): {} {}'.format(len(fm), fm))
    print ('  FITS files: {} {}'.format(anyfits, ff))
    if (anyfits > 0):
        print ('FOUND FITS FILES - SKIPPING THIS DIR')
        return 0

    # loop and load metadata files.  I'm assuming that normally there
    # is only one per dierctory, but just in case have the loop
    # option.
    if (len(fm) <= 0):
        print ('No metadata file in this directory')
        md = None
    else:
        for ifm in fm:
            md = r.GPUMeta(ifm)
            v1 = md.antenna_pos()
            print ('  META - antpos - {}'.format(v1[0]))


    # loop and load spectrum files
    ct = 0
    for ifs in fs:
        
        sp = r.GPUSpec(ifs)
        lut = sp.start_ut()
        # print ('{} {}'.format(lut, lut.isoformat()))
        sdf_getobs_spec (sp, md)
        
        if (ct %100 == 0):
            ut, ob, ex, sc, so = sp.fits_hdr()
            print ('  M+S - {} {} {} {}'.\
                   format(ct, ut,
                          md.antenna_pos_at_time(ut)['fields']['az'],
                          md.antenna_pos_at_time(ut)['fields']['el']))
        ct += 1

    # ensure that each array in obs_spec is in increasing time sort order
    # set up separate list of datetime as the sort index
    #  zip together all the other obs_spec lists after the sort index
    # sort and then copy back into obs_spec.

    obs_spec = sort_dict_of_lists (obs_spec, 'datetime')
    
    #j = sorted (obs_spec.keys())
    #tmp_sort_arr = obs_spec['datetime']
    #tmpspec = zip(tmp_sort_arr, *(obs_spec[k] for k in j))
    #srtspec = map(list, zip(*sorted(tmpspec)))
    #sidx = 1
    #for k in j:
    #    obs_spec[k] = srtspec[sidx]
    #    sidx += 1

    print ('End {}'.format(dt.datetime.now().ctime()))
    print ('')
        
    return ct

def load_noise(idnum, d, fn, fm, ff):
    """
    Overall driver to load in noise files in nth directory in the list
    idnum == n'th directory - currently not used
    d == dir path
    fn == list of noise files
    fm == list of meta files
    ff == list of fits files
    [NOT YET IMPLEMENTED OPTION:
      maxper == max number of spectra to insert in a fits file. If < 0, do all.
    ]
    """
    global obs_nois
    
    anyfits = len(ff)
        
    print ('Start {}'.format(dt.datetime.now().ctime()))
    print ('Dir: {}'.format(d))
    print ('  Noise files: {}'.format(len(fn)))
    print ('  Metadata file(s): {} {}'.format(len(fm), fm))
    print ('  FITS files: {} {}'.format(anyfits, ff))
    if (anyfits > 0):
        print ('FOUND FITS FILES - SKIPPING THIS DIR')
        return 0

    # loop and load metadata files.  I'm assuming that normally there
    # is only one per dierctory, but just in case have the loop
    # option.
    if (len(fm) <= 0):
        print ('No metadata file in this directory')
        md = None
    else:
        for ifm in fm:
            md = r.GPUMeta(ifm)
            v1 = md.antenna_pos()
            print ('  META - antpos - {}'.format(v1[0]))


    # loop and load noise files
    ct = 0
    for ifn in fn:
        
        npw = r.GPUNoise(ifn)
        lut = npw.start_ut()
        # print ('{} {}'.format(lut, lut.isoformat()))
        sdf_getobs_nois (npw, md)
        
        if (ct %100 == 0):
            ut, ob, ex, sc, so = npw.fits_hdr()
            print ('  M+S - {} {} {} {}'.\
                   format(ct, ut,
                          md.antenna_pos_at_time(ut)['fields']['az'],
                          md.antenna_pos_at_time(ut)['fields']['el']))
        ct += 1
        
    # ensure that each array in obs_spec is in increasing time sort order
    # set up separate list of datetime as the sort index
    #  zip together all the other obs_spec lists after the sort index
    # sort and then copy back into obs_spec.

    obs_nois = sort_dict_of_lists (obs_nois, 'datetime')
    
    print ('End {}'.format(dt.datetime.now().ctime()))
    print ('')
        
    return ct

#------------------------------------------------------------------------
# Execute as script

if __name__ == '__main__':
    import sys

    # Pull in the command line
    # expect argv[0] == script, [1] == output file name
    argv = sys.argv
    argc = len(argv)

    if (argc < 2):
        print ('{}'.format(__usage__))
    else:
        a = loop_over_dirs(argv[1])

