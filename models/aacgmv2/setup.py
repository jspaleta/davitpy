from distutils.core import setup, Extension
import os

rst = os.environ['RSTPATH']
leo = os.environ['AACGMV2PATH']
setup (name = "aagcmlibv2",
       version = "0.1",
       description = "wrapper to call c AACGM code:",
       author = "Jef Spaleta",
       author_email = "jdspaleta@alaska.edu",
       url = "",
       long_description =
"""
wrapper to call new c AACGM coefficents developed by Simon Shepard: For full information see: code:http://thayer.dartmouth.edu/superdarn/aacgm.html
""",
       classifiers=[
  ],

       ext_modules = [Extension("aacgmlibv2",
                                sources=[ "aacgmlib_v2.c",
                                     leo+"/aacgmlib_v2.c",
                                     ],
                                include_dirs = [
                                     leo,
                                     ],
                               )
                     ]
      )

