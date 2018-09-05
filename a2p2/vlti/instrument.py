#!/usr/bin/env python

__all__ = []

import os
import json
import collections
from a2p2.apis import Instrument
from a2p2.vlti.gui import VltiUI


class VltiInstrument(Instrument):
    def  __init__(self, facility, insname):
        Instrument.__init__(self, facility, insname)
        self.facility = facility
        self.ui = facility.ui
        
        # use in latter lazy initialisation
        self.rangeTable = None
        self.ditTable = None
        
    def get(self, obj, fieldname, defaultvalue):
        if fieldname in obj._fields:
            return getattr(obj,fieldname)
        else:
            return defaultvalue
    
    def getCoords(self, target, requirePrecision=True):
        """ 
        Format coordinates from given target to be VLTI conformant. 
        Throws an exception if requirePrecision is true and given inputs have less than 3 (RA) or 2 (DEC) digits.
        """
        
        NAME = target.name
        
        RA = target.RA
        w = RA.rfind('.')
        l = len(RA)
        if l-w < 4 and requirePrecision:
            raise ValueError ("Object " + NAME + " has a too low precision in RA to be useable by VLTI, please correct with 3 or more digits.")
        if l-w > 4:
            RA = RA[0:w + 4]
            
        DEC = target.DEC
        w = DEC.rfind('.')
        l = len(DEC)
        if l-w < 3 and requirePrecision:
            raise ValueError ("Object " + NAME + " has a too low precision in DEC to be useable by VLTI,please correct with 2 or more digits.")
        if l-w > 4:
            DEC = DEC[0:w + 4]
            
        return RA, DEC
    
    def getPMCoords(self, target, defaultPMRA=0.0, defaultPMDEC=0.0):
        """
        Returns PMRA, PMDEC as float values rounded to 4 decimal digits. 0.0 is used as default if not present.
        """
        PMRA = self.get( target, "PMRA", defaultPMRA ) 
        PMDEC = self.get( target, "PMDEC", defaultPMDEC )
        return round( float(PMRA) / 1000.0, 4 ), round( float(PMDEC) / 1000.0, 4 )
    
    def getFlux(self, target, flux):
        """
        Returns Flux as float values rounded to 3 decimal digits.
        
        flux in 'V', 'J', 'H'...
        """
        return round(float(getattr(target,"FLUX_"+flux)), 3)
    

# ditTable and rangeTable are extracted from online doc:
# -- https://www.eso.org/sci/facilities/paranal/instruments/gravity/doc/Gravity_TemplateManual.pdf
# they are saved in json and displayed in the Help on application startup

#k = 'GRAVITY_gen_acq.tsf'
# using collections.OrderedDict to keep the order of keys:
#rangeTable[k] = collections.OrderedDict({})
#rangeTable[k]['SEQ.FI.HMAG']={'min':-10., 'max':20., 'default':0.0}
#...

    def getDitTable(self):
        if self.ditTable:
            return self.ditTable
        f = os.path.join(self.facility.getConfDir(),self.getName()+"_ditTable.json")
        self.ditTable = json.load(open(f))
        return self.ditTable
    
    def formatDitTable(self):
        ditTable = self.getDitTable()
        buffer = '    Mode     |Spec |  Pol  |Tel |       K       | DIT(s)\n'
        buffer +='--------------------------------------------------------\n'
        for tel in ['AT']:
            for spec in ['MED', 'HIGH']:
                for pol in ['OUT', 'IN']:
                    for i in range(len(ditTable[tel][spec][pol]['DIT'])):
                        buffer += 'Single Field | %4s | %3s | %2s |'%(spec, pol, tel)
                        buffer += ' %4.1f <K<= %3.1f | %4.1f'%(ditTable[tel][spec][pol]['MAG'][i],
                                                     ditTable[tel][spec][pol]['MAG'][i+1],
                                                     ditTable[tel][spec][pol]['DIT'][i])
                        buffer += "\n"                             
            Kdf = ditTable[tel]['Kdf']
            Kut = ditTable[tel]['Kut']
            buffer +=' Dual Field  |  all | all | %2s | Kdf = K - %.1f |  -\n'%(tel,Kdf)
            tel="UT"
            buffer +='Single Field |  all | all | %2s | Kdf = K - %.1f |  -\n'%(tel,Kut)
            buffer +=' Dual Field  |  all | all | %2s | Kdf = K - %.1f |  -\n'%(tel,Kut + Kdf)            
        return buffer
        
    def getDit(self, tel, spec, pol, K, dualFeed=False, showWarning=False):
        """
        finds DIT according to ditTable and K magnitude K

        'tel' in "AT" or "UT" 
        'spec' in ditTable[tel].keys()
        'pol' in ditTable[tel][spec].keys()

        * does not manage out of range (returns None) *        
        """
        #TODO add LOW mode  as new 'spec' entry for Gravity   
        if spec == "LOW":
            spec="MED"            
        if showWarning and spec == "LOW":
            self.ui.ShowWarningMessage("DIT table does not provide LOW values. Using MED as workarround.")
        ditTable = self.getDitTable()
        mags = ditTable["AT"][spec][pol]['MAG']
        dits = ditTable["AT"][spec][pol]['DIT']
        if dualFeed:
            dK = ditTable["AT"]['Kdf']
        else:
            dK = 0.0
        if tel == "UT":
            dK += ditTable["AT"]['Kut']
            
        for i,d in enumerate(dits):
            if mags[i]<(K-dK) and (K-dK)<=mags[i+1]:
                return d
        return None
    
    def getRangeTable(self):        
        if self.rangeTable:
            return self.rangeTable
        f = os.path.join(self.facility.getConfDir(), self.getName()+"_rangeTable.json")
        # TODO use .tmp.json keys 
        # using collections.OrderedDict to keep the order of keys:
        self.rangeTable = json.load(open(f), object_pairs_hook=collections.OrderedDict)
        return self.rangeTable

    def isInRange(self, tpl, key, value):
        """
        check if "value" is in range of keyword "key" for template "tpl"

        ValueError raised if key or tpl is not found.
        """
        rangeTable = self.getRangeTable()
        _tpl = ''
        # -- find relevant range dictionnary
        for k in rangeTable.keys():
            if tpl in [l.strip() for l in k.split(',')]:
                _tpl = k
        if _tpl == '':
            raise ValueError("unknown template '%s'" % tpl)
        if not key in rangeTable[_tpl].keys():
            raise ValueError("unknown keyword '%s' in template '%s'"%(key, tpl))            
        if 'min' in rangeTable[_tpl][key].keys() and \
           'max' in rangeTable[_tpl][key].keys():
           return value>=rangeTable[_tpl][key]['min'] and\
                  value<=rangeTable[_tpl][key]['max']
        if 'list' in rangeTable[_tpl][key].keys():
            return value in rangeTable[_tpl][key]['list']
        if 'spaceseparatedlist' in rangeTable[_tpl][key].keys():
            for e in value.split(" "):
                if not e in rangeTable[_tpl][key]['spaceseparatedlist']:
                    return False
            return True
        # no range provided in tsf file
        return True
    
    def getRange(self, tpl, key):
        """
        returns range of keyword "key" for template "tpl"

        ValueError raised if key or tpl is not found.
        """
        rangeTable = self.getRangeTable()
        _tpl = ''
        # -- find relevant range dictionnary
        for k in rangeTable.keys():
            if tpl in [l.strip() for l in k.split(',')]:
                _tpl = k
        if _tpl == '':
            raise ValueError("unknown template '%s'" % tpl)
        if not key in rangeTable[_tpl].keys():
            raise ValueError("unknown keyword '%s' in template '%s'"%(key, tpl))          
        if 'min' in rangeTable[_tpl][key].keys() and \
           'max' in rangeTable[_tpl][key].keys():
           return (rangeTable[_tpl][key]['min'], rangeTable[_tpl][key]['max'])
        if 'list' in rangeTable[_tpl][key].keys():
            return rangeTable[_tpl][key]['list']
        if 'spaceseparatedlist' in rangeTable[_tpl][key].keys():
            for e in value.split(" "):
                return rangeTable[_tpl][key]['spaceseparatedlist']
            
    def getRangeDefaults(self, tpl):
        """
        returns a dict of keywords/default values for template "tpl"

        ValueError raised if tpl is not found.
        """
        rangeTable = self.getRangeTable()
        _tpl = ''
        # -- find relevant range dictionnary
        for k in rangeTable.keys():
            if tpl in [l.strip() for l in k.split(',')]:
                _tpl = k
        if _tpl == '':
            raise ValueError("unknown template '%s'" % tpl)
        res={}
        for key in rangeTable[_tpl].keys():
            if 'default' in rangeTable[_tpl][key].keys():
                res[key]=rangeTable[_tpl][key]["default"]
        return res
    
    def formatRangeTable(self):
        rangeTable = self.getRangeTable()
        buffer = ""
        for l in rangeTable.keys():
            buffer += l + "\n"
            for k in rangeTable[l].keys():
                constraint = rangeTable[l][k]
                keys = constraint.keys()
                buffer += ' %30s :' % ( k )
                if 'min' in keys and 'max' in keys:
                    buffer += ' %f ... %f ' % ( constraint['min'], constraint['max'])
                elif 'list' in keys:
                    buffer += str(constraint['list'])
                elif "spaceseparatedlist" in keys:
                    buffer += ' ' + " ".join(constraint['spaceseparatedlist'])
                if 'default' in keys:
                    buffer += ' (' + str(constraint['default']) + ')'
                else:
                    buffer +=' -no default-'
                buffer += "\n"
        return buffer
                    
    def getSkyDiff(ra, dec, ftra, ftdec):
        science = SkyCoord(ra, dec, frame='icrs', unit='deg')
        ft = SkyCoord(ftra, ftdec, frame='icrs', unit='deg')
        ra_offset = (science.ra - ft.ra) * np.cos(ft.dec.to('radian'))
        dec_offset = (science.dec - ft.dec)
        return [ra_offset.deg * 3600 * 1000, dec_offset.deg * 3600 * 1000] #in mas
     
    def getHelp(self):
        s  = self.getName()
        s += "\n\nRangeTable:\n"
        s += self.formatRangeTable()
        s += "\n\nDitTable:\n"
        s += self.formatDitTable()
        return s
    
    def getTemplateName(self, templateType, dualField, OBJTYPE):
        objType="calibrator"
        if OBJTYPE and "SCI" in OBJTYPE:
            objType="exp"
        field="single"
        if dualField:
            field="dual"        
        if OBJTYPE:
            return "_".join((self.getName(), field, templateType, objType))        
        return "_".join((self.getName(), field, templateType))
    
    def getObsTemplateName(self, OBJTYPE, dualField=False):
        return self.getTemplateName("obs", dualField, OBJTYPE )
    
    def getAcqTemplateName(self, dualField=False, OBJTYPE=None):
        return self.getTemplateName("acq", dualField, OBJTYPE)
    

# TemplateSignatureFile
# new style class to get __getattr__ advantage
class TSF(object): 
    def __init__(self, instrument, tpl):
        self.tpl = tpl
        self.instrument = instrument
        supportedTpl = instrument.getRangeTable().keys()
        

        # set default values for every keywords
# next 2 lines are probably unuseful
#        if tpl not in supportedTpl:
#            raise ValueError ("template '%s' is not in the instrument range table. Must be one of %s" % (tpl, str(supportedTpl)))
        self.tsfParams = self.instrument.getRangeDefaults(tpl)
        
        self.__initialised = True
        # after initialisation, setting attributes is the same as setting an item
        
    def set(self, key, value, checkRange=True):
        if checkRange:
            if not self.instrument.isInRange(self.tpl, key, value):
                raise ValueError("Parameter value (%s) is out of range for keyword %s in template %s "%(str(value), key, self.tpl))        
        # TODO check that key is valid when checkRange is False
        self.tsfParams[key] = value
    
    def get(self, key):
        # TODO offer to get default value
        return self.tsfParams[key]
    
    def getDict(self):
        return self.tsfParams
    
    def __getattr__(self, name): # called for non instance attributes (i.e. keywords)
        rname = name.replace('_','.')  
        if rname in self.tsfParams :
            return self.tsfParams[rname]
        else:
            raise AttributeError("unknown keyword '%s' in template '%s'"%(rname, self.tpl)) 


    def __setattr__(self, name, value):
        if self.__dict__.has_key(name) :  # any normal attributes are handled normal           
            return object.__setattr__(self, name, value)
        if not self.__dict__.has_key('_TSF__initialised'):  # this test allows attributes to be set in the __init__ method 
            return object.__setattr__(self, name, value)
  
        # continue with keyword try
        rname = name.replace('_','.') 
        self.set(rname,value)
        
    def __str__(self):
        buffer = "TemplateSignatureFile: "
        buffer += str(self.tsfParams)
        return buffer
        
    
        
class ConstraintSet:
    # We could image to get a checking mecanism such as TSF
    def __init__(self):
        self.constraints={}
        self.constraints['name']='Aspro-created constraint'
    
    def setSeeing(self,value):
        self.constraints['seeing']=value
    
    def setSkyTransparency(self,value):
        self.constraints['skyTransparency'] = value
    
    def setBaseline(self, value):
        self.constraints['baseline'] = value
        
    def setAirmass(self, value):
        self.constraints['airmass'] = value
        
    def setFli(self, value):
        self.constraints['fli'] = value
        
    def getDict(self):
        return self.constraints
    
    def __str__(self):
        buffer = "ConstraintSet: "
        buffer += str(self.constraints)
        return buffer

class FixedDict(object):
    
    def __init__(self, keys):
        self.myKeys = keys
        self.myValues = {}
        self.__initialised = True
        # after initialisation, setting attributes is the same as setting an item
    
    def getDict(self):
        return self.myValues
        
    def __getattr__(self, name): # called for non instance attributes (i.e. keywords)
        rname = name.replace('_','.')  
        if rname in self.myValues :
            return self.myValues[rname]
        else:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if self.__dict__.has_key(name) :  # any normal attributes are handled normally
            #print("set1 %s to %s"%(name, str(value)))
            return object.__setattr__(self, name, value)
        if not self.__dict__.has_key('_FixedDict__initialised'):  # this test allows attributes to be set in the __init__ method 
            #print("set2 %s to %s"%(name, str(value)))
            return object.__setattr__(self, name, value)
  
        # continue with keyword try
        #print("set3 %s to %s"%(name, str(value)))
        rname = name.replace('_','.') 
        if rname in self.myKeys :
            self.myValues[name] = value
        else:
            raise ValueError("keyword %s is not part of supported ones %s "%(name, self.myKeys))    
        

class OBTarget(FixedDict):
   
   def __init__(self):
       FixedDict.__init__(self, ('name', 'ra', 'dec', 'properMotionRa', 'properMotionDec'))
       # keys must be synchronized with p2 
     