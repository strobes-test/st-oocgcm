#!/usr/bin/env python
#
"""modelgrids module.
Define classes that give acces to model grid metrics and operators
(e.g. gradients)

This submodule is still under development. See the project
[wiki page](https://github.com/lesommer/oocgcm/wiki/modelgrids_design)

"""

import numpy as np
import numpy.ma as ma
from netCDF4 import Dataset
import xarray as xr

from collections import Iterable

try:
    import dask.array as da
    has_dask = True
except ImportError:
    has_dask = False


class generic_netcdf_loader_for_grids:
    """Method for loading netcdf files
    """
    def __init__(self,array_type=None,chunks=None):
        self.array_type = array_type
        self.chunks = chunks

    def __call__(self,filename=None,varname=None):
	if self.array_type == 'numpy':
            out = Dataset(filename).variables[varname][:].squeeze()
        elif self.array_type == 'xarray':
            ds = xr.open_dataset(filename,chunks=self.chunks,lock=False)
            out = ds[varname]
	elif self.array_type == 'dask_from_numpy':
	    d = Dataset(filename).variables[varname][:].squeeze()
	    out = da.from_array(np.array(d), chunks=self.chunks)
        elif self.array_type == 'dask_from_netcdf':
            d = Dataset(filename).variables[varname]
            out = da.from_array(d, chunks=self.chunks)
        return out

class generic_grid:
    """Base class implementing differential operators
    """
    def __init__(self):
	pass

    def load_horizontal_metrics(self):
        self.e1t = self._load(self.coordfile,varname='e1t')
        self.e2t = self._load(self.coordfile,varname='e2t')
        self.e1u = self._load(self.coordfile,varname='e1u')
        self.e2u = self._load(self.coordfile,varname='e2u')
        self.e1v = self._load(self.coordfile,varname='e1v')
        self.e2v = self._load(self.coordfile,varname='e2v')
	self.shape = self.e1t.shape # with dask ?


    def gradh(self,q):
        """Return the 2D gradient of a scalar field.
            input :  on T-grid
            output : on U-grid and V-grid
         """
        gx = self.d_i(q) / self.e1u
        gy = self.d_j(q) / self.e2v
        #
        return gx,gy



class nemo_grid_with_numpy_arrays(generic_grid):
    """Define a grid object holding metric terms and all the methods
    related to the grid.
    numpy version : for grids that fit in memory.
    """
    def __init__(self, coordfile=None):
        generic_grid.__init__(self)
        self.coordfile = coordfile
        self.define_array_type_specific_functions()
        self.load_horizontal_metrics()

    def define_array_type_specific_functions(self):
	self._load = generic_netcdf_loader_for_grids(array_type='numpy')
        self._concatenate = np.concatenate
	self._zeros = np.zeros

    def d_i(self,q):
        """Return the difference q(i+1) - q(i)"""
        di = np.roll(q,-1,axis=-1) - q
        return di

    def d_j(self,q):
        """Return the difference q(j+1) - q(j)"""
        dj = np.roll(q,-1,axis=-2) - q
        return dj

class nemo_grid_with_dask_arrays(generic_grid):
    """Define a grid object holding metric terms and all the methods
    related to the grid.
    dask (from array) version : for grids that fit in memory but with
    parralelized operations.
    """
    def __init__(self, coordfile=None,chunks=(1000,1000),
                 array_type='dask_from_netcdf'):
	"""Two types of array :
            - array_type='dask_from_netcdf'
	        - array_type='dask_from_numpy'
	"""
	self.chunks = chunks
	self._array_type = array_type
        generic_grid.__init__(self)
        self.coordfile = coordfile
        self.define_array_type_specific_functions()
        self.load_horizontal_metrics()
        self.define_overlap_operations()

    def define_array_type_specific_functions(self):
        self._load = generic_netcdf_loader_for_grids\
			(array_type=self._array_type,chunks=self.chunks)
        self._zeros = lambda n:da.zeros(n,chunks=self.chunks)

    def define_overlap_operations(self):
        """Define grid operations requiring exchanges among chuncks
        """
        self._d_i = lambda q:np.roll(q,-1,axis=-1) - q
        self._d_j = lambda q:np.roll(q,-1,axis=-2) - q

    def d_i(self,q):
        """Return the difference q(i+1) - q(i)"""
        diq = q.map_overlap(self._d_i, depth=1,boundary=0).compute()
        return diq

    def d_j(self,q):
        """Return the difference q(j+1) - q(j)"""
        djq = q.map_overlap(self._d_j, depth=1,boundary=0).compute()
        return djq

class nemo_grid_with_xarray(generic_grid):
    """Define a grid object holding metric terms and all the methods
    related to the grid.
    x-array version : for grids that do not fit in memory.
    """
    def __init__(self, coordfile=None,chunks=None):
	self.chunks = chunks
        generic_grid.__init__(self)
        self.coordfile = coordfile
        self.define_array_type_specific_functions()
        self.load_horizontal_metrics()

    def define_array_type_specific_functions(self):
        self._load = generic_netcdf_loader_for_grids\
			                  (array_type='xarray',chunks=self.chunks)
        self._zeros = lambda n : xr.DataArray(np.zeros(n))

    def d_i(self,q):
        """Return the difference q(i+1) - q(i)"""
        di = q.shift(x=-1) - q
        return di

    def d_j(self,q):
        """Return the difference q(j+1) - q(j)"""
        dj = q.shift(y=-1) - q # works with chunks too
        return dj
