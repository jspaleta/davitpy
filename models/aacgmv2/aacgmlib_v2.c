#include <Python.h>
#include <datetime.h>
#include <zlib.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <string.h>
#include <fcntl.h>
#include <math.h>
#include "aacgmlib_v2.h"

#if PY_VERSION_HEX < 0x02050000
  typedef int Py_ssize_t;
#endif

static PyObject *
Convert(PyObject *self, PyObject *args)
{
	
	double inlat, inlon, height, outLat, outLon, r; 
	int flg;
	
	if(!PyArg_ParseTuple(args, "dddi", &inlat,&inlon,&height,&flg))
		return NULL;
	else
	{
		inlon = fmod(inlon, 360.);
		AACGM_v2_Convert(inlat, inlon, height, &outLat, &outLon, &r, flg);
		 
		return Py_BuildValue("ddd", outLat, outLon, r);
	}
	
}

static PyObject *
SetDateTime(PyObject *self, PyObject *args)
{
	
	int year,month,day,hour,minute,second; 
        PyObject *dt=NULL;

	if(!PyArg_ParseTuple(args, "O", &dt))
		return NULL;
	else {
		if(PyDateTime_Check(dt)) { 
			year=PyDateTime_GET_YEAR(dt);
			month=PyDateTime_GET_MONTH(dt);
			day=PyDateTime_GET_DAY(dt);
			hour=PyDateTime_DATE_GET_HOUR(dt);
			minute=PyDateTime_DATE_GET_MINUTE(dt);
			second=PyDateTime_DATE_GET_SECOND(dt);
			AACGM_v2_SetDateTime(year,month,day,hour,minute,second);
			Py_RETURN_TRUE;
		} else {
			return NULL;
		}
	}
	
}

static PyObject *
GetDateTime(PyObject *self)
{
	
	int year,month,day,hour,minute,second,dayno; 
        PyObject *dt=NULL;
	AACGMGetDateTime(&year,&month,&day,&hour,&minute,&second,&dayno);
        dt=PyDateTime_FromDateAndTime(year,month,day,hour,minute,second,0);
	return dt;
	
}


 
static PyMethodDef aacgmv2Methods[] = 
{
	{"convert",  Convert, METH_VARARGS, "convert to aacgm coords\nformat: lat, lon, r = convert(inLat, inLon, height, flg)\nheight in km; flg=0: geo to aacgm; flg=1: aacgm to geo"},
	{"setDateTime",  SetDateTime, METH_VARARGS, "set the Datetime for aacgm to use internally"},
	{"getDateTime",  GetDateTime, 0, "get the Datetime aacgm uses internally"},
	{NULL, NULL, 0, NULL}        /* Sentinel */
};

PyMODINIT_FUNC
initaacgmlibv2(void)
{
        PyDateTime_IMPORT;
	(void) Py_InitModule("aacgmlibv2", aacgmv2Methods);
}
