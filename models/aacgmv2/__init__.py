"""
*********************
**Module**: models.leo_aacgm
*********************
"""
try:
    from aacgmlibv2 import *
except Exception, e:
    print __file__+' -> aacgmlibv2: ', e
import datetime
lat = -80 
lon = -23.5
hgt = 350.
geo = 0
now=datetime.datetime.utcnow()
print "Setting date to now:",now
setDateTime(now)
print "using date:",getDateTime()
print "hgt",hgt
print "lat",lat
print "lon",lon
print "convert"
mlat,mlon,altitude=convert(lat,lon,hgt,geo)

print mlat,mlon,altitude
