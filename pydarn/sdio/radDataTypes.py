# Copyright (C) 2012  VT SuperDARN Lab
# Full license can be found in LICENSE.txt
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
.. module:: radDataTypes
   :synopsis: the classes needed for reading, writing, and storing fundamental radar data (iq,raw,fit)
.. moduleauthor:: AJ, 20130108
*********************
**Module**: pydarn.sdio.radDataTypes
*********************
**Classes**:
  * :class:`pydarn.sdio.radDataTypes.radDataPtr`
  * :class:`pydarn.sdio.radDataTypes.radBaseData`
  * :class:`pydarn.sdio.radDataTypes.scanData`
  * :class:`pydarn.sdio.radDataTypes.beamData`
  * :class:`pydarn.sdio.radDataTypes.prmData`
  * :class:`pydarn.sdio.radDataTypes.fitData`
  * :class:`pydarn.sdio.radDataTypes.rawData`
  * :class:`pydarn.sdio.radDataTypes.iqData`
"""


from utils import twoWayDict
alpha = ['a','b','c','d','e','f','g','h','i','j','k','l','m', \
          'n','o','p','q','r','s','t','u','v','w','x','y','z']


class radDataPtr():
  """A class which contains a pipeline to a data source
  
  **Public Attrs**:
    * **sTime** (`datetime <http://tinyurl.com/bl352yx>`_): start time of the request
    * **eTime** (`datetime <http://tinyurl.com/bl352yx>`_): end time of the request
    * **stid** (int): station id of the request
    * **channel** (str): channel of the request
    * **bmnum** (int): beam number of the request
    * **cp** (int): control prog id of the request
    * **fType** (str): the file type, 'fitacf', 'rawacf', 'iqdat', 'fitex', 'lmfit'
    * **fBeam** (:class:`pydarn.sdio.radDataTypes.beamData`): the first beam of the next scan, useful for when reading into scan objects
    * **recordIndex** (dict): look up dictionary for file offsets for all records 
    * **scanStartIndex** (dict): look up dictionary for file offsets for scan start records
  **Private Attrs**:
    * **ptr** (file or mongodb query object): the data pointer (different depending on mongodo or dmap)
    * **fd** (int): the file descriptor 
    * **filtered** (bool): use Filtered datafile 
    * **nocache** (bool):  do not use cached files, regenerate tmp files 
    * **src** (str):  local or sftp 

  **Methods**:
    * **open** 
    * **close** 
    * **seek** 
    * **readRec** 
    * **readScan** 
    * **readAll** 
    
  Written by AJ 20130108
  """
  def __init__(self,sTime=None,radcode=None,eTime=None,stid=None,channel=None,bmnum=None,cp=None, \
                fileType=None,filtered=False, src=None,fileName=None,noCache=False):
    import datetime as dt
    import os,glob,string
    from pydarn.radar import network
    import utils
    import paramiko as p
    import re
    
    self.sTime = sTime
    self.eTime = eTime
    self.stid = stid
    self.channel = channel
    self.bmnum = bmnum
    self.cp = cp
    self.fType = fileType
    self.dType = None
    self.fBeam = None
    self.recordIndex = None
    self.scanStartIndex = None
    self.__filename = fileName 
    self.__filtered = filtered
    self.__nocache  = noCache
    self.__src = src
    self.__fd = None
    self.__ptr =  None

    #check inputs
    assert(isinstance(sTime,dt.datetime)), \
      'error, sTime must be datetime object'
    assert(eTime == None or isinstance(eTime,dt.datetime)), \
      'error, eTime must be datetime object or None'
    assert(channel == None or (isinstance(channel,str) and len(channel) == 1)), \
      'error, channel must be None or a 1-letter string'
    assert(bmnum == None or isinstance(bmnum,int)), \
      'error, bmnum must be an int or None'
    assert(cp == None or isinstance(cp,int)), \
      'error, cp must be an int or None'
    assert(fileType == 'rawacf' or fileType == 'fitacf' or \
      fileType == 'fitex' or fileType == 'lmfit' or fileType == 'iqdat'), \
      'error, fileType must be one of: rawacf,fitacf,fitex,lmfit,iqdat'
    assert(fileName == None or isinstance(fileName,str)), \
      'error, fileName must be None or a string'
    assert(isinstance(filtered,bool)), \
      'error, filtered must be True of False'
    assert(src == None or src == 'local' or src == 'sftp'), \
      'error, src must be one of None,local,sftp'

    if radcode is not None:
      assert(isinstance(radcode,str)), \
        'error, radcode must be None or a string'
      segments=radcode.split(".")
      try: rad=segments[0]
      except: rad=None
      try: chan=segments[1]
      except: chan=None
      assert(isinstance(rad,str) and len(rad) == 3), \
        'error, rad must be a 3 char string'
      self.stid=int(network().getRadarByCode(rad).id)

    if(self.eTime == None):
      self.eTime = self.sTime+dt.timedelta(days=1)

    filelist = []
    if(fileType == 'fitex'): arr = ['fitex','fitacf','lmfit']
    elif(fileType == 'fitacf'): arr = ['fitacf','fitex','lmfit']
    elif(fileType == 'lmfit'): arr = ['lmfit','fitex','fitacf']
    else: arr = [fileType]

    #move back a little in time because files often start at 2 mins after the hour
    sTime = sTime-dt.timedelta(minutes=4)
    #a temporary directory to store a temporary file
    try:
      tmpDir=os.environ['DAVIT_TMPDIR']
    except:
      tmpDir = '/tmp/sd/'
    d = os.path.dirname(tmpDir)
    if not os.path.exists(d):
      os.makedirs(d)

    cached = False
    fileSt = None

    #FIRST, check if a specific filename was given
    if fileName != None:
        try:
            if(not os.path.isfile(fileName)):
                print 'problem reading',fileName,':file does not exist'
                return None
            outname = tmpDir+str(int(utils.datetimeToEpoch(dt.datetime.now())))
            if(string.find(fileName,'.bz2') != -1):
                outname = string.replace(fileName,'.bz2','')
                print 'bunzip2 -c '+fileName+' > '+outname+'\n'
                os.system('bunzip2 -c '+fileName+' > '+outname)
            elif(string.find(fileName,'.gz') != -1):
                outname = string.replace(fileName,'.gz','')
                print 'gunzip -c '+fileName+' > '+outname+'\n'
                os.system('gunzip -c '+fileName+' > '+outname)
            else:
                os.system('cp '+fileName+' '+outname)
                print 'cp '+fileName+' '+outname
            filelist.append(outname)
            self.dType = 'dmap'
            fileSt = sTime
        except Exception, e:
            print e
            print 'problem reading file',fileName
            return None
    #Next, check for a cached file
    if fileName == None and not noCache:
        try:
            if True:
                for f in glob.glob("%s????????.??????.????????.??????.%s.%sf" % (tmpDir,radcode,fileType)):
                    try:
                        ff = string.replace(f,tmpDir,'')
                        #check time span of file
                        t1 = dt.datetime(int(ff[0:4]),int(ff[4:6]),int(ff[6:8]),int(ff[9:11]),int(ff[11:13]),int(ff[13:15]))
                        t2 = dt.datetime(int(ff[16:20]),int(ff[20:22]),int(ff[22:24]),int(ff[25:27]),int(ff[27:29]),int(ff[29:31]))
                        #check if file covers our timespan
                        if t1 <= sTime and t2 >= eTime:
                            cached = True
                            filelist.append(f)
                            print 'Found cached file: %s' % f
                            break
                    except Exception,e:
                        print e
            if not cached:
                for f in glob.glob("%s????????.??????.????????.??????.%s.%s" % (tmpDir,radcode,fileType)):
                    try:
                        ff = string.replace(f,tmpDir,'')
                        #check time span of file
                        t1 = dt.datetime(int(ff[0:4]),int(ff[4:6]),int(ff[6:8]),int(ff[9:11]),int(ff[11:13]),int(ff[13:15]))
                        t2 = dt.datetime(int(ff[16:20]),int(ff[20:22]),int(ff[22:24]),int(ff[25:27]),int(ff[27:29]),int(ff[29:31]))
                        #check if file covers our timespan
                        if t1 <= sTime and t2 >= eTime:
                            cached = True
                            filelist.append(f)
                            print 'Found cached file: %s' % f
                            break
                    except Exception,e:
                        print e
        except Exception,e:
            print e
    #Next, LOOK LOCALLY FOR FILES
    if not cached and (src == None or src == 'local') and fileName == None:
        try:
            for ftype in arr:
                print "\nLooking locally for %s files : rad %s chan: %s" % (ftype,radcode,chan)
                #deal with UAF naming convention by using the radcode
                fnames = ['*.%s.%s*' % (radcode,ftype)]
                for form in fnames:
                    #iterate through all of the hours in the request
                    #ie, iterate through all possible file names
                    ctime = sTime.replace(minute=0)
                    if(ctime.hour % 2 == 1): ctime = ctime.replace(hour=ctime.hour-1)
                    while ctime <= eTime:
                        #directory on the data server
                        ##################################################################
                        ### IF YOU ARE A USER NOT AT VT, YOU PROBABLY HAVE TO CHANGE THIS
                        ### TO MATCH YOUR DIRECTORY STRUCTURE
                        ##################################################################
                        localdict={}
                        try:
                            localdict["dirtree"]=os.environ['DAVIT_LOCALDIR']
                        except:
                            localdict["dirtree"]="/sd-data/"
                        localdict["year"] = "%04d" % ctime.year
                        localdict["month"]= "%02d" % ctime.month
                        localdict["day"]  = "%02d" % ctime.day
                        localdict["ftype"]  = ftype
                        localdict["radar"]  = rad
                        try:
                            localdirformat = os.environ['DAVIT_DIRFORMAT']
                            myDir = localdirformat % localdict
                        except:
                            myDir = '/sd-data/'+ctime.strftime("%Y")+'/'+ftype+'/'+rad+'/'
                        hrStr = ctime.strftime("%H")
                        dateStr = ctime.strftime("%Y%m%d")
                        print myDir
                        #iterate through all of the files which begin in this hour
                        for filename in glob.glob(myDir+dateStr+'.'+hrStr+form):
                            outname = string.replace(filename,myDir,tmpDir)
                            #unzip the compressed file
                            if(string.find(filename,'.bz2') != -1):
                                outname = string.replace(outname,'.bz2','')
                                print 'bunzip2 -c '+filename+' > '+outname+'\n'
                                os.system('bunzip2 -c '+filename+' > '+outname)
                            elif(string.find(filename,'.gz') != -1):
                                outname = string.replace(outname,'.gz','')
                                print 'gunzip -c '+filename+' > '+outname+'\n'
                                os.system('gunzip -c '+filename+' > '+outname)
                            else:
                                command='cp '+filename+' '+outname
                                print command
                                os.system(command)

                            filelist.append(outname)
                            print outname
                            #HANDLE CACHEING NAME
                            ff = string.replace(outname,tmpDir,'')
                            #check the beginning time of the file (for cacheing)
                            t1 = dt.datetime(int(ff[0:4]),int(ff[4:6]),int(ff[6:8]),int(ff[9:11]),int(ff[11:13]),int(ff[14:16]))
                            if fileSt == None or t1 < fileSt: fileSt = t1
                        ##################################################################
                        ### END SECTION YOU WILL HAVE TO CHANGE
                        ##################################################################
                        ctime = ctime+dt.timedelta(hours=1)
                    if(len(filelist) > 0):
                        print 'found',ftype,'data in local files'
                        self.fType,self.dType = ftype,'dmap'
                        fileType = ftype
                        break
                if(len(filelist) > 0): break
                else:
                    print  'could not find',ftype,'data in local files'
        except Exception, e:
            print e
            print 'problem reading local data, perhaps you are not at VT?'
            print 'you probably have to edit radDataRead.py'
            print 'I will try to read from other sources'
            src=None
    #finally, check the VT sftp server if we have not yet found files
    if (src == None or src == 'sftp') and self.__ptr == None and len(filelist) == 0 and fileName == None:
        for ftype in arr:
            print '\nLooking on the remote SFTP server for',ftype,'files'
            try:
                #deal with UAF naming convention
                fnames = ['..........'+ftype]
                if(channel == None): fnames.append('..\...\....\.a\.')
                else: fnames.append('..........'+channel+'.'+ftype)
                for form in fnames:
                    #create a transport object for use in sftp-ing
                    transport = p.Transport((os.environ['VTDB'], 22))
                    transport.connect(username=os.environ['DBREADUSER'],password=os.environ['DBREADPASS'])
                    sftp = p.SFTPClient.from_transport(transport)

                    #iterate through all of the hours in the request
                    #ie, iterate through all possible file names
                    ctime = sTime.replace(minute=0)
                    if ctime.hour % 2 == 1: ctime = ctime.replace(hour=ctime.hour-1)
                    oldyr = ''
                    while ctime <= eTime:
                        #directory on the data server
                        myDir = '/data/'+ctime.strftime("%Y")+'/'+ftype+'/'+rad+'/'
                        hrStr = ctime.strftime("%H")
                        dateStr = ctime.strftime("%Y%m%d")
                        if(ctime.strftime("%Y") != oldyr):
                            #get a list of all the files in the directory
                            allFiles = sftp.listdir(myDir)
                            oldyr = ctime.strftime("%Y")
                        #create a regular expression to find files of this day, at this hour
                        regex = re.compile(dateStr+'.'+hrStr+form)
                        #go thorugh all the files in the directory
                        for aFile in allFiles:
                            #if we have a file match between a file and our regex
                            if(regex.match(aFile)):
                                print 'copying file '+myDir+aFile+' to '+tmpDir+aFile
                                filename = tmpDir+aFile
                                #download the file via sftp
                                sftp.get(myDir+aFile,filename)
                                #unzip the compressed file
                                if(string.find(filename,'.bz2') != -1):
                                    outname = string.replace(filename,'.bz2','')
                                    print 'bunzip2 -c '+filename+' > '+outname+'\n'
                                    os.system('bunzip2 -c '+filename+' > '+outname)
                                elif(string.find(filename,'.gz') != -1):
                                    outname = string.replace(filename,'.gz','')
                                    print 'gunzip -c '+filename+' > '+outname+'\n'
                                    os.system('gunzip -c '+filename+' > '+outname)
                                else:
                                    print 'It seems we have downloaded an uncompressed file :/'
                                    print 'Strange things might happen from here on out...'

                                filelist.append(outname)

                                #HANDLE CACHEING NAME
                                ff = string.replace(outname,tmpDir,'')
                                #check the beginning time of the file
                                t1 = dt.datetime(int(ff[0:4]),int(ff[4:6]),int(ff[6:8]),int(ff[9:11]),int(ff[11:13]),int(ff[14:16]))
                                if fileSt == None or t1 < fileSt: fileSt = t1
                        # Ctime increment needs to happen outside of the aFile loop.
                        ctime = ctime+dt.timedelta(hours=1)
                    if len(filelist) > 0 :
                        print 'found',ftype,'data on sftp server'
                        self.fType,self.dType = ftype,'dmap'
                        fileType = ftype
                        break
                if len(filelist) > 0 : break
                else:
                    print  'could not find',ftype,'data on sftp server'
            except Exception,e:
                print e
                print 'problem reading from sftp server'
    #check if we have found files
    if len(filelist) != 0:
        #concatenate the files into a single file
        if not cached:
            print 'Concatenating all the files in to one'
            #choose a temp file name with time span info for cacheing
            tmpName = '%s%s.%s.%s.%s.%s.%s' % (tmpDir, \
              fileSt.strftime("%Y%m%d"),fileSt.strftime("%H%M%S"), \
              eTime.strftime("%Y%m%d"),eTime.strftime("%H%M%S"),radcode,fileType)
            print 'cat '+string.join(filelist)+' > '+tmpName
            os.system('cat '+string.join(filelist)+' > '+tmpName)
            for filename in filelist:
                print 'rm '+filename
                os.system('rm '+filename)
        else:
            tmpName = filelist[0]
            self.fType = fileType
            self.dType = 'dmap'

        #filter(if desired) and open the file
        if(not filtered):
            self.open(tmpName)
        else:
            if not fileType+'f' in tmpName:
                try:
                    fTmpName = tmpName+'f'
                    print 'fitexfilter '+tmpName+' > '+fTmpName
                    os.system('fitexfilter '+tmpName+' > '+fTmpName)
                except Exception,e:
                    print 'problem filtering file, using unfiltered'
                    fTmpName = tmpName
            else:
                fTmpName = tmpName
            try:
                self.open(fTmpName)
            except Exception,e:
                print 'problem opening file'
                print e
    if(self.__ptr != None):
        if(self.dType == None): self.dType = 'dmap'
    else:
        print '\nSorry, we could not find any data for you :('




  def __repr__(self):
    myStr = 'radDataPtr: \n'
    for key,var in self.__dict__.iteritems():
      if isinstance(var,radBaseData) or isinstance(var,radDataPtr) or  isinstance(var,type({})):
        myStr += '%s = %s \n' % (key,'object')
      else:
        myStr += '%s = %s \n' % (key,var)
    return myStr

  def __del__(self):
    self.close() 


  def __iter__(self):
    return self

  def next(self):
    beam=self.readRec()
    if beam is None:
      raise StopIteration
    else:
      return beam


  def open(self,filename):
      """open a dmap file by filename."""
      import os
      self.__filename=filename
      self.__fd = os.open(filename,os.O_RDONLY)
      self.__ptr = os.fdopen(self.__fd)

  def createIndex(self):
      import datetime as dt
      from pydarn.dmapio import getDmapOffset,readDmapRec,setDmapOffset
      recordDict={}
      scanStartDict={}
      starting_offset=self.offsetTell()
      #rewind back to start of file
      self.rewind()
      while(1):
          #read the next record from the dmap file
          offset= getDmapOffset(self.__fd)
          dfile = readDmapRec(self.__fd)
          if(dfile is None):
              #if we dont have valid data, clean up, get out
              print '\nreached end of data'
              break
          else:
              if(dt.datetime.utcfromtimestamp(dfile['time']) >= self.sTime and \
                dt.datetime.utcfromtimestamp(dfile['time']) <= self.eTime) : 
                  rectime = dt.datetime.utcfromtimestamp(dfile['time'])
                  recordDict[rectime]=offset
                  if dfile['scan']==1: scanStartDict[rectime]=offset
      #reset back to before building the index 
      self.offsetSeek(starting_offset)
      self.recordIndex=recordDict
      self.scanStartIndex=scanStartDict
      return recordDict,scanStartDict

  def offsetSeek(self,offset):
      """jump to dmap record at supplied byte offset. 
      """
      from pydarn.dmapio import setDmapOffset 
      return setDmapOffset(self.__fd,offset)

  def offsetTell(self):
      """jump to dmap record at supplied byte offset. 
      """
      from pydarn.dmapio import getDmapOffset,setDmapOffset
      return getDmapOffset(self.__fd)

  def rewind(self):
      """jump to beginning of dmap file."""
      from pydarn.dmapio import setDmapOffset 
      return setDmapOffset(self.__fd,0)

  def readScan(self):
      """A function to read a full scan of data from a :class:`pydarn.sdio.radDataTypes.radDataPtr` object
  
      .. note::
        This will ignore any bmnum request.  Also, if no channel was specified in radDataOpen, it will only read channel 'a'

      **Returns**:
        * **myScan** (:class:`pydarn.sdio.radDataTypes.scanData`): an object filled with the data we are after.  *will return None when finished reading*
    
      """
      from pydarn.sdio import scanData
      #Save the radDataPtr's bmnum setting temporarily and set it to None
      orig_beam=self.bmnum
      self.bmnum=None

      if self.__ptr.closed:
          print 'error, your file pointer is closed'
          return None

      myScan = scanData()
      myBeam=self.readRec()
      if(myBeam.prm.scan == 1):  
        firstflg=True
        myScan.append(myBeam)
      else:
        if self.fBeam != None:
          myScan.append(self.fBeam)
          firstflg = False
        else:
          firstflg = True

      while(1):
        myBeam=self.readRec()
        if myBeam is None: 
          break
        if(myBeam.prm.scan == 0 or firstflg):
          myScan.append(myBeam)
          firstflg = False
          continue
        else:
          self.fBeam = myBeam
          break 
      self.bmnum=orig_beam

      return myScan



  def readRec(self):
     """A function to read a single record of radar data from a :class:`pydarn.sdio.radDataTypes.radDataPtr` object
     **Returns**:
     * **myBeam** (:class:`pydarn.sdio.radDataTypes.beamData`): an object filled with the data we are after.  *will return None when finished reading*
     """
     from pydarn.sdio.radDataTypes import radDataPtr, beamData, \
     fitData, prmData, rawData, iqData, alpha
     import pydarn, datetime as dt

     #check input
     if(self.__ptr == None):
         print 'error, your pointer does not point to any data'
         return None
     if self.__ptr.closed:
         print 'error, your file pointer is closed'
         return None
     myBeam = beamData()
     #do this until we reach the requested start time
     #and have a parameter match
     while(1):
         offset=pydarn.dmapio.getDmapOffset(self.__fd)
         dfile = pydarn.dmapio.readDmapRec(self.__fd)
         #check for valid data
         if dfile == None or dt.datetime.utcfromtimestamp(dfile['time']) > self.eTime:
             #if we dont have valid data, clean up, get out
             print '\nreached end of data'
             #self.close()
             return None
         #check that we're in the time window, and that we have a 
         #match for the desired params
         if dfile['channel'] < 2: channel = 'a'
         else: channel = alpha[dfile['channel']-1]
         if(dt.datetime.utcfromtimestamp(dfile['time']) >= self.sTime and \
               dt.datetime.utcfromtimestamp(dfile['time']) <= self.eTime and \
               (self.stid == None or self.stid == dfile['stid']) and
               (self.channel == None or self.channel == channel) and
               (self.bmnum == None or self.bmnum == dfile['bmnum']) and
               (self.cp == None or self.cp == dfile['cp'])):
             #fill the beamdata object
             myBeam.updateValsFromDict(dfile)
             myBeam.recordDict=dfile
             myBeam.fType = self.fType
             myBeam.fPtr = self
             myBeam.offset = offset
             #file prm object
             myBeam.prm.updateValsFromDict(dfile)
             if myBeam.fType == "rawacf":
                 myBeam.rawacf.updateValsFromDict(dfile)
             if myBeam.fType == "iqdat":
                 myBeam.iqdat.updateValsFromDict(dfile)
             if(myBeam.fType == 'fitacf' or myBeam.fType == 'fitex' or myBeam.fType == 'lmfit'):
                 myBeam.fit.updateValsFromDict(dfile)
             if myBeam.fit.slist == None:
                 myBeam.fit.slist = []
             return myBeam

  def close(self):
    """close associated dmap file."""
    import os
    if self.__ptr is not None:
      self.__ptr.close()
      self.__fd=None

class radBaseData():
  """a base class for the radar data types.  This allows for single definition of common routines
  
  **ATTRS**:
    * Nothing.
  **METHODS**:
    * :func:`updateValsFromDict`: converts a dict from a dmap file to radBaseData
    
  Written by AJ 20130108
  """
  
  def copyData(self,obj):
    """This method is used to recursively copy all of the contents from ont object to self
    
    .. note::
      In general, users will not need to use this.
      
    **Args**: 
      * **obj** (:class:`pydarn.sdio.radDataTypes.radBaseData`): the object to be copied
    **Returns**:
      * Nothing.
    **Example**:
      ::
      
        myradBaseData.copyData(radBaseDataObj)
      
    written by AJ, 20130402
    """
    for key, val in obj.__dict__.iteritems():
      if isinstance(val, radBaseData):
        try: getattr(self, key).copyData(val)
        except: pass
      else:
        setattr(self,key,val)

  def updateValsFromDict(self, aDict):
    """A function to to fill a radar params structure with the data in a dictionary that is returned from the reading of a dmap file
    
    .. note::
      In general, users will not need to us this.
      
    **Args**:
      * **aDict (dict):** the dictionary containing the radar data
    **Returns**
      * nothing.
      
    Written by AJ 20121130
    """
    
    import datetime as dt
    
    #iterate through prmData's attributes
    for attr, value in self.__dict__.iteritems():
      #check for special params
      if(attr == 'time'):
        #convert from epoch to datetime
        if(aDict.has_key(attr) and isinstance(aDict[attr], float)): 
          setattr(self,attr,dt.datetime.utcfromtimestamp(aDict[attr]))
        continue
      elif(attr == 'channel'):
        if(aDict.has_key('channel')): 
          if(isinstance(aDict.has_key('channel'), int)):
            if(aDict['channel'] < 2): self.channel = 'a'
            else: self.channel = alpha[aDict['channel']-1]
          else: self.channel = aDict['channel']
        else: self.channel = 'a'
        continue
      elif(attr == 'inttus'):
        if(aDict.has_key('intt.us')): 
          self.inttus = aDict['intt.us']
        continue
      elif(attr == 'inttsc'):
        if(aDict.has_key('intt.sc')): 
          self.inttsc = aDict['intt.sc']
        continue
      elif(attr == 'noisesky'):
        if(aDict.has_key('noise.sky')): 
          self.noisesky = aDict['noise.sky']
        continue
      elif(attr == 'noisesearch'):
        if(aDict.has_key('noise.search')): 
          self.noisesearch = aDict['noise.search']
        continue
      elif(attr == 'noisemean'):
        if(aDict.has_key('noise.mean')): 
          self.noisemean = aDict['noise.mean']
        continue
      elif(attr == 'acfd' or attr == 'xcfd'):
        if(aDict.has_key(attr)): 
          setattr(self,attr,[])
          for i in range(self.parent.prm.nrang):
            rec = []
            for j in range(self.parent.prm.mplgs):
              samp = []
              for k in range(2):
                samp.append(aDict[attr][(i*self.parent.prm.mplgs+j)*2+k])
              rec.append(samp)
            getattr(self, attr).append(rec)
        else: setattr(self,attr,[])
        continue
      elif(attr == 'mainData'):
        if(aDict.has_key('data')): 
          if(len(aDict['data']) == aDict['smpnum']*aDict['seqnum']*2*2): fac = 2
          else: fac = 1
          setattr(self,attr,[])
          for i in range(aDict['seqnum']):
            rec = []
            for j in range(aDict['smpnum']):
              samp = []
              for k in range(2):
                samp.append(aDict['data'][(i*fac*aDict['smpnum']+j)*2+k])
              rec.append(samp)
            getattr(self, attr).append(rec)
        else: setattr(self,attr,[])
        continue
      elif(attr == 'intData'):
        if(aDict.has_key('data')): 
          if(len(aDict['data']) == aDict['smpnum']*aDict['seqnum']*2*2): fac = 2
          else: continue
          setattr(self,attr,[])
          for i in range(aDict['seqnum']):
            rec = []
            for j in range(aDict['smpnum']):
              samp = []
              for k in range(2):
                samp.append(aDict['data'][((i*fac+1)*aDict['smpnum']+j)*2+k])
              rec.append(samp)
            getattr(self, attr).append(rec)
        else: setattr(self,attr,[])
        continue
      try:
        setattr(self,attr,aDict[attr])
      except:
        #put in a default value if not another object
        if(not isinstance(getattr(self,attr),radBaseData)):
          setattr(self,attr,None)
          
  #def __repr__(self):
    #myStr = ''
    #for key,var in self.__dict__.iteritems():
      #if(isinstance(var,radBaseData) and key != 'parent'):
        #print key
        #myStr += key+'\n'
        #myStr += str(var)
      #else:
        #myStr += key+' = '+str(var)+'\n'
    #return myStr
    
class scanData(list):
  """a class to contain a radar scan.  Extends list.  Just a list of :class:`pydarn.sdio.radDataTypes.beamData` objects
  
  **Attrs**:
    Nothing.
  **Example**: 
    ::
    
      myBeam = pydarn.sdio.scanData()
    
  Written by AJ 20121130
  """

  def __init__(self):
    pass
  
class beamData(radBaseData):
  """a class to contain the data from a radar beam sounding, extends class :class:`pydarn.sdio.radDataTypes.radBaseData`
  
  **Attrs**:
    * **cp** (int): radar control program id number
    * **stid** (int): radar station id number
    * **time** (`datetime <http://tinyurl.com/bl352yx>`_): timestamp of beam sounding
    * **channel** (str): radar operating channel, eg 'a', 'b', ...
    * **bmnum** (int): beam number
    * **prm** (:class:`pydarn.sdio.radDataTypes.prmData`): operating params
    * **fit** (:class:`pydarn.sdio.radDataTypes.fitData`): fitted params
    * **rawacf** (:class:`pydarn.sdio.radDataTypes.rawData`): rawacf data
    * **iqdat** (:class:`pydarn.sdio.radDataTypes.iqData`): iqdat data
    * **fType** (str): the file type, 'fitacf', 'rawacf', 'iqdat', 'fitex', 'lmfit'

  **Example**: 
    ::
    
      myBeam = pydarn.sdio.radBeam()
    
  Written by AJ 20121130
  """
  def __init__(self, beamDict=None, myBeam=None, proctype=None):
    #initialize the attr values
    self.cp = None
    self.stid = None
    self.time = None
    self.bmnum = None
    self.channel = None
    self.exflg = None
    self.lmflg = None
    self.acflg = None
    self.rawflg = None
    self.iqflg = None
    self.fitex = None
    self.fitacf = None
    self.lmfit= None
    self.fit = fitData()
    self.rawacf = rawData(parent=self)
    self.prm = prmData()
    self.iqdat = iqData()
    self.recordDict = None 
    self.fType = None
    self.offset = None
    self.fPtr = None 
    #if we are intializing from an object, do that
    if(beamDict != None): self.updateValsFromDict(beamDict)
    
  def __repr__(self):
    import datetime as dt
    myStr = 'Beam record FROM: '+str(self.time)+'\n'
    for key,var in self.__dict__.iteritems():
      if isinstance(var,radBaseData) or isinstance(var,radDataPtr) or isinstance(var,type({})):
        myStr += '%s  = %s \n' % (key,'object')
      else:
        myStr += '%s  = %s \n' % (key,var)
    return myStr
    
class prmData(radBaseData):
  """A class to represent radar operating parameters, extends :class:`pydarn.sdio.radDataTypes.radBaseData`

  **Attrs**:
    * **nave**  (int): number of averages
    * **lagfr**  (int): lag to first range in us
    * **smsep**  (int): sample separation in us
    * **bmazm**  (float): beam azimuth
    * **scan**  (int): new scan flag
    * **rxrise**  (int): receiver rise time
    * **inttsc**  (int): integeration time (sec)
    * **inttus**  (int): integration time (us)
    * **mpinc**  (int): multi pulse increment (tau, basic lag time) in us
    * **mppul**  (int): number of pulses
    * **mplgs**  (int): number of lags
    * **mplgexs**  (int): number of lags (tauscan)
    * **nrang**  (int): number of range gates
    * **frang**  (int): first range gate (km)
    * **rsep**  (int): range gate separation in km
    * **xcf**  (int): xcf flag
    * **tfreq**  (int): transmit freq in kHz
    * **txpl**  (int): transmit pulse length in us 
    * **ifmode**  (int): if mode flag
    * **ptab**  (mppul length list): pulse table
    * **ltab**  (mplgs x 2 length list): lag table
    * **noisemean**  (float): mean noise level
    * **noisesky**  (float): sky noise level
    * **noisesearch**  (float): freq search noise level

  Written by AJ 20121130
  """

  #initialize the struct
  def __init__(self, prmDict=None, myPrm=None):
    #set default values
    self.nave = None        #number of averages
    self.lagfr = None       #lag to first range in us
    self.smsep = None       #sample separation in us
    self.bmazm = None       #beam azimuth
    self.scan = None        #new scan flag
    self.rxrise = None      #receiver rise time
    self.inttsc = None      #integeration time (sec)
    self.inttus = None      #integration time (us)
    self.mpinc = None       #multi pulse increment (tau, basic lag time) in us
    self.mppul = None       #number of pulses
    self.mplgs = None       #number of lags
    self.mplgexs = None     #number of lags (tauscan)
    self.nrang = None       #number of range gates
    self.frang = None       #first range gate (km)
    self.rsep = None        #range gate separation in km
    self.xcf = None         #xcf flag
    self.tfreq = None       #transmit freq in kHz
    self.txpl = None       #transmit freq in kHz
    self.ifmode = None      #if mode flag
    self.ptab = None        #pulse table
    self.ltab = None        #lag table
    self.noisemean = None   #mean noise level
    self.noisesky = None    #sky noise level
    self.noisesearch = None #freq search noise level
    
    #if we are copying a structure, do that
    if(prmDict != None): self.updateValsFromDict(prmDict)

  def __repr__(self):
    import datetime as dt
    myStr = 'Prm data: \n'
    for key,var in self.__dict__.iteritems():
      myStr += '%s  = %s \n' % (key,var)
    return myStr

class fitData(radBaseData):
  """a class to contain the fitted params of a radar beam sounding, extends :class:`pydarn.sdio.radDataTypes.radBaseData`
  
  **Attrs**:
    * **pwr0**  (prm.nrang length list): lag 0 power
    * **slist**  (npnts length list): list of range gates with backscatter
    * **npnts** (int): number of range gates with scatter
    * **nlag**  (npnts length list): number of good lags
    * **qflg**  (npnts length list): quality flag
    * **gflg**  (npnts length list): ground scatter flag
    * **p_l**  (npnts length list): lambda power
    * **p_l_e**  (npnts length list): lambda power error
    * **p_s**  (npnts length list): sigma power
    * **p_s_e**  (npnts length list): sigma power error
    * **v**  (npnts length list): velocity
    * **v_e**  (npnts length list): velocity error
    * **w_l**  (npnts length list): lambda spectral width
    * **w_l_e**  (npnts length list): lambda width error
    * **w_s**  (npnts length list): sigma spectral width
    * **w_s_e**  (npnts length list): sigma width error
    * **phi0**  (npnts length list): phi 0
    * **phi0_e**  (npnts length list): phi 0 error
    * **elv**  (npnts length list): elevation angle
  
  **Example**: 
    ::
    
      myFit = pydarn.sdio.fitData()
    
  Written by AJ 20121130
  """

  #initialize the struct
  def __init__(self, fitDict=None, myFit=None):
    self.pwr0 = None      #lag 0 power
    self.slist = None     # list of range gates with backscatter
    self.npnts = None     #number of range gates with scatter
    self.nlag = None      #number of good lags
    self.qflg = None      #quality flag
    self.gflg = None      #ground scatter flag
    self.p_l = None       #lambda power
    self.p_l_e = None     #lambda power error
    self.p_s = None       #sigma power
    self.p_s_e = None     #sigma power error
    self.v = None         #velocity
    self.v_e = None       #velocity error
    self.w_l = None       #lambda spectral width
    self.w_l_e = None     #lambda width error
    self.w_s = None       #sigma spectral width
    self.w_s_e = None     #sigma width error
    self.phi0 = None      #phi 0
    self.phi0_e = None    #phi 0 error
    self.elv = None       #elevation angle
    
    if(fitDict != None): self.updateValsFromDict(fitDict)

  def __repr__(self):
    import datetime as dt
    myStr = 'Fit data: \n'
    for key,var in self.__dict__.iteritems():
      myStr += '%s = %s \n' % (key,var)
    return myStr

class rawData(radBaseData):
  """a class to contain the rawacf data from a radar beam sounding, extends :class:`pydarn.sdio.radDataTypes.radBaseData`
  
  **Attrs**:
    * **pwr0** (nrang length list): acf lag0 pwr 
    * **acfd** (nrang x mplgs x 2 length list): acf data
    * **xcfd** (nrang x mplgs x 2 length list): xcf data
  
  **Example**: 
    ::
    
      myRaw = pydarn.sdio.rawData()
    
  Written by AJ 20130125
  """

  #initialize the struct
  def __init__(self, rawDict=None, parent=None):
    self.pwr0 = []      #acf data
    self.acfd = []      #acf data
    self.xcfd = []      #xcf data
    self.parent = parent #reference to parent beam
    
    if(rawDict != None): self.updateValsFromDict(rawDict)

  def __repr__(self):
    import datetime as dt
    myStr = 'Raw data: \n'
    for key,var in self.__dict__.iteritems():
      myStr += '%s = %s \n' % (key,var)
    return myStr

class iqData(radBaseData):
  """ a class to contain the iq data from a radar beam sounding, extends :class:`pydarn.sdio.radDataTypes.radBaseData`
  
  .. warning::
    I'm not sure what all of the attributes mean.  if somebody knows what these are, please help!

  **Attrs**:
    * **chnnum** (int): number of channels?
    * **smpnum** (int): number of samples per pulse sequence
    * **skpnum** (int): number of samples to skip at the beginning of a pulse sequence?
    * **seqnum** (int): number of pulse sequences
    * **tbadtr** (? length list): time of bad tr samples?
    * **tval** (? length list): ?
    * **atten** (? length list): ?
    * **noise** (? length list): ?
    * **offset** (? length list): ?
    * **size** (? length list): ?
    * **badtr** (? length list): bad tr samples?
    * **mainData** (seqnum x smpnum x 2 length list): the actual iq samples (main array)
    * **intData** (seqnum x smpnum x 2 length list): the actual iq samples (interferometer)
  
  **Example**: 
    ::
    
      myIq = pydarn.sdio.iqData()
    
  Written by AJ 20130116
  """

  #initialize the struct
  def __init__(self, iqDict=None, parent=None):
    self.seqnum = None
    self.chnnum = None
    self.smpnum = None
    self.skpnum = None
    self.btnum = None
    self.tsc = None
    self.tus = None
    self.tatten = None
    self.tnoise = None
    self.toff = None
    self.tsze = None
    self.tbadtr = None
    self.badtr = None
    self.mainData = []
    self.intData = []
    
    if(iqDict != None): self.updateValsFromDict(iqDict)

  def __repr__(self):
    import datetime as dt
    myStr = 'IQ data: \n'
    for key,var in self.__dict__.iteritems():
      myStr += '%s = %s \n' % (key,var)
    return myStr

if __name__=="__main__":
  import os
  import datetime
  import hashlib
  try:
      tmpDir=os.environ['DAVIT_TMPDIR']
  except:
      tmpDir = '/tmp/sd/'

  rad='fhe'
  channel=None
  fileType='fitacf'
  filtered=False
  sTime=datetime.datetime(2012,11,1,0,0)
  eTime=datetime.datetime(2012,11,1,4,0)
  expected_filename="20121031.220100.20121101.040000.fhe.fitacf"
  expected_path=os.path.join(tmpDir,expected_filename)
  expected_filesize=26684193
  expected_md5sum="9de702d7a0371b9e53f6ea01c076eccb"
  print "Expected File:",expected_path

  print "\nRunning sftp grab example for radDataPtr."
  print "Environment variables used:"
  print "  VTDB:", os.environ['VTDB']
  print "  DBREADUSER:", os.environ['DBREADUSER']
  print "  DBREADPASS:", os.environ['DBREADPASS']
  src='sftp'
  if os.path.isfile(expected_path):
    os.remove(expected_path)
  VTptr = radDataPtr(sTime,rad,eTime=eTime,channel=channel,bmnum=None,cp=None,fileType=fileType,filtered=filtered, src=src,noCache=True)
  if os.path.isfile(expected_path):
    statinfo = os.stat(expected_path)
    print "Actual File Size:  ", statinfo.st_size
    print "Expected File Size:", expected_filesize 
    md5sum=hashlib.md5(expected_path).hexdigest()
    print "Actual Md5sum:  ",md5sum
    print "Expected Md5sum:",expected_md5sum
    if expected_md5sum!=md5sum:
      print "Error: Cached dmap file has unexpected md5sum."
  else:
    print "Error: Failed to create expected cache file"
  VTptr.close()
  del VTptr

  print "\nRunning local grab example for radDataPtr."
  print "Environment variables used:"
  print "  DAVIT_LOCALDIR:", os.environ['DAVIT_LOCALDIR']
  print "  DAVIT_DIRFORMAT:", os.environ['DAVIT_DIRFORMAT']
  src='local'
  if os.path.isfile(expected_path):
    os.remove(expected_path)
  localptr = radDataPtr(sTime,rad,eTime=eTime,channel=channel,bmnum=None,cp=None,fileType=fileType,filtered=filtered, src=src,noCache=True)
  if os.path.isfile(expected_path):
    statinfo = os.stat(expected_path)
    print "Actual File Size:  ", statinfo.st_size
    print "Expected File Size:", expected_filesize 
    md5sum=hashlib.md5(expected_path).hexdigest()
    print "Actual Md5sum:  ",md5sum
    print "Expected Md5sum:",expected_md5sum
    if expected_md5sum!=md5sum:
      print "Error: Cached dmap file has unexpected md5sum."
  else:
    print "Error: Failed to create expected cache file"
  localptr.close()
  del localptr

