#!python3
# -*- coding: utf-8 -*-
"""
------------------------------------------------------------------------------

 This script generates an empty dummy 4 dimensional data cube in fits format.
 After the initialisation this cube gets filled with fits image data. The
 cube header gets updated from the first image in `env.dirImages`.
 This script can be used to generate fits data cubes of sizes that exceeds the
 machine's RAM (tested with 234 GB RAM and 335 GB cube data).

------------------------------------------------------------------------------

 Developed at: IDIA (Institure for Data Intensive Astronomy), Cape Town, ZA
 Inspired by: https://github.com/idia-astro/image-generator
 
 Lennart Heino

------------------------------------------------------------------------------
"""

import csv
import datetime
import itertools
#import logging
#from logging import info, error
import os
import re
import shutil
import sys
from glob import glob

import click
import numpy as np
from astropy.io import fits

from frocc.config import FILEPATH_CONFIG_TEMPLATE, FILEPATH_CONFIG_USER
from frocc.lhelpers import (SEPERATOR, DotMap,
                            calculate_channelFreq_from_header,
                            change_channelNumber_from_filename,
                            get_channelNumber_from_filename,
                            get_config_in_dot_notation,
                            get_dict_from_click_args,
                            get_lowest_channelNo_with_data_in_cube,
                            get_std_via_mad, main_timer,
                            update_fits_header_of_cube)
from frocc.logger import *

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# SETTINGS

#logging.basicConfig(
#    format="%(asctime)s\t[ %(levelname)s ]\t%(message)s", level=logging.INFO
#)

# SETTINGS
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


def make_empty_image(conf, mode="normal"):
    """
    Generate an empty dummy fits data cube.

    The data cube dimensions are derived from the cube images.

    """
    cubeNameInput = os.path.join(conf.input.dirOutput, conf.input.basename + conf.env.extCubeSmoothedFits)
    cubeNameOutput = os.path.join(conf.input.dirOutput, conf.input.basename + conf.env.extCubeAveragemapFits)
        
    info(SEPERATOR)
    info(f"Getting image dimension for data cube from: {cubeNameInput}")
    hduCubeInput = fits.open(cubeNameInput, memmap=True, mode="update")
    xdim, ydim = np.squeeze(hduCubeInput[0].data).shape[-2:]

    info("X-dimension: %s", xdim)
    info("Y-dimension: %s", ydim)

    zdim = 1
    info(f"Z-dimension: {zdim}")

    info("Assuming full Stokes for dimension W.")
    wdim = 3
    info("W-dimension: %s", wdim)

    dims = tuple([xdim, ydim, zdim, wdim])

    # create header

    dummy_dims = tuple(1 for d in dims)
    #dummy_data = np.ones(dummy_dims, dtype=np.float64) * np.nan
    #dummy_data = dummy_data.fill(np.nan)
    dummy_data = np.zeros(dummy_dims, dtype=np.float32)
    hdu = fits.PrimaryHDU(data=dummy_data)

    header = hduCubeInput[0].header
    for i, dim in enumerate(dims, 1):
        header["NAXIS%d" % i] = dim


    header.tofile(cubeNameOutput, overwrite=True)

    # create full-sized zero image

    header_size = len(
        header.tostring()
    )  # Probably 2880. We don't pad the header any more; it's just the bare minimum
    data_size = np.product(dims) * np.dtype(np.float32).itemsize
    # This is not documented in the example, but appears to be Astropy's default behaviour
    # Pad the total file size to a multiple of the header block size
    block_size = 2880
    data_size = block_size * (((data_size -1) // block_size) + 1)

    with open(cubeNameOutput, "rb+") as f:
        f.seek(header_size + data_size - 1)
        f.write(b"\0")




def write_statistics_file(statsDict, conf, mode="normal"):
    """
    Takes the dictionary with Stokes I and V RMS noise and writes it to a file.

    Parameters
    ----------
    rmdDict: dict of lists with floats
       Dictionary with lists for Stokes I and V rms noise

    """
    # Outputs a statistics file with estimates for RMS noise in Stokes I and V
    filepathStatistics = conf.input.basename + conf.env.extCubeAveragemapStatistics
    legendList = ["chanNo", "frequency [MHz]", "weight [Jy^-2]"]
    info("Writing statistics file: %s", filepathStatistics)
    with open(filepathStatistics, "w") as csvFile:
        writer = csv.writer(csvFile, delimiter="\t")
        csvData = [legendList]
        for ii, entry in enumerate(statsDict["chanNo"]):
            chanNo = statsDict["chanNo"][ii]
            freq = round(statsDict["frequency"][ii] * 1e-6, 4)
            weight = round(statsDict["weight"][ii] * 1e-6, 4)
            csvData.append([chanNo, freq, weight])
        writer.writerows(csvData)

def fill_cube_with_images(conf, mode="normal"):
    """
    Fills the empty data cube with fits data.


    """

    cubeNameInput = os.path.join(conf.input.dirOutput, conf.input.basename + conf.env.extCubeSmoothedFits)
    cubeNameOutput = os.path.join(conf.input.dirOutput, conf.input.basename + conf.env.extCubeAveragemapFits)

    info(SEPERATOR)
    info(f"Opening data cube: {cubeNameInput}")
    hudCubeInput = fits.open(cubeNameInput, memmap=True, ignore_missing_end=True, mode="update")
    dataCubeInput = hudCubeInput[0].data

    info(f"Opening data cube: {cubeNameOutput}")
    hudCubeOutput = fits.open(cubeNameOutput, memmap=True, ignore_missing_end=True, mode="update")
    dataCubeOutput = hudCubeOutput[0].data

    highestChannel = int(dataCubeInput.shape[1])

    statsDict = {}
    statsDict["chanNo"] = []
    statsDict["weight"] = []
    statsDict["frequency"] = []
    for ii in range(0, highestChannel):
        if np.isnan(np.sum(dataCubeInput[3, ii, :, :])):
            w = np.nan
        else:
            info(f"Getting RMS from Stokes V for channel {ii}")
            rms = get_std_via_mad(dataCubeInput[3, ii, :, :])
            w = 1/(rms**2)
        calcFreq = calculate_channelFreq_from_header(hudCubeInput[0].header, ii)
        statsDict["frequency"].append(calcFreq)
        statsDict["weight"].append(w)
        statsDict["chanNo"].append(ii)

    P_I = dataCubeOutput[0, 0, :, :]
    P_QU = dataCubeOutput[1, 0, :, :]
    P_V = dataCubeOutput[2, 0, :, :]
    weightedFreqs = 0
    for ii, w in enumerate(statsDict["weight"]):
        info(f"Processing average maps: Progress {ii+1}/{len(statsDict['weight'])}")
        if not np.isnan(w):
            I = dataCubeInput[0, ii, :, :]
            Q = dataCubeInput[1, ii, :, :]
            #info(f"Q: Progress {Q}")
            U = dataCubeInput[2, ii, :, :]
            V = dataCubeInput[3, ii, :, :]
            P_I += w * I
            P_QU += w * np.sqrt(Q**2 + U**2)
            #info(f"P_QU: Progress {P_QU}")
            P_V += w * V
            weightedFreqs += w * np.sqrt(statsDict["frequency"][ii]**2)
    weightsSum = np.nansum(statsDict["weight"])
    dataCubeOutput[0, 0, :, :] = P_I / weightsSum
    dataCubeOutput[1, 0, :, :] = P_QU / weightsSum
    dataCubeOutput[2, 0, :, :] = P_V / weightsSum
    averagedFreq = np.nansum(weightedFreqs) / weightsSum

    hudCubeInput.close()
    hudCubeOutput.close()

    addFitsHeaderDict = {
        "CRPIX3": 1,
        "NAXIS3": 1,
        "CRVAL3": averagedFreq,
        }
    update_fits_header_of_cube(cubeNameOutput, addFitsHeaderDict)
    write_statistics_file(statsDict, conf, mode=mode)

    # make a copy to the hdf5 output directory
    try:
        shutil.copyfile(cubeNameOutput, os.path.join(conf.input.dirHdf5Output, os.path.basename(cubeNameOutput)))
    except shutil.SameFileError:
        pass




#@click.command(context_settings=dict(
#    ignore_unknown_options=True,
#    allow_extra_args=True,
#))
##@click.argument('--inputMS', required=False)
#@click.pass_context
@main_timer
def main():
    #args = DotMap(get_dict_from_click_args(ctx.args))
    conf = get_config_in_dot_notation(templateFilename=FILEPATH_CONFIG_TEMPLATE, configFilename=FILEPATH_CONFIG_USER)
    if conf.input.smoothbeam:
        info(f"Scripts config: {conf}")
        make_empty_image(conf, mode="normal")
        fill_cube_with_images(conf, mode="normal")
    else:
        info(f"No `smoothbeam` specified. Skipping, not creating an average map.")



if __name__ == "__main__":
    main()
