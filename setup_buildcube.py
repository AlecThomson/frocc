import sys
import logging
import datetime
import os
from logging import info, error

# own helpers
from lhelpers import get_dict_from_click_args, DotMap, get_config_in_dot_notation, main_timer, write_sbtach_file

# need to be instaled in container. Right now linkt with $PYTHONPATH
import click

# non defaults
import numpy as np
from casatools import msmetadata


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# SETTINGS

logging.basicConfig(
    format="%(asctime)s\t[ %(levelname)s ]\t%(message)s", level=logging.INFO
)
SEPERATOR = "-----------------------------------------------------------------"

FILEPATH_CONFIG_USER = "default_config.txt"
FILEPATH_CONFIG_TEMPLATE = "default_config.template"

# SETTINGS
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# HELPER
def get_all_freqsList(conf):
    """
    Get all the frequencies of all the sub-channels in each spw.
    """
    allFreqsList = np.array([])
    info("""Opening file to read the frequencies of all sub-channels in each spw: {0}""".format(conf.input.inputMS))
    msmd = msmetadata()
    msmd.open(msfile=conf.input.inputMS, maxcache=10000)
    for spw in range(0, msmd.nspw()):
        allFreqsList = np.append(allFreqsList, (msmd.chanfreqs(spw) + msmd.chanwidths(spw)))
        allFreqsList = np.append(allFreqsList, (msmd.chanfreqs(spw) - msmd.chanwidths(spw)))
    return allFreqsList


def get_fieldnames(conf):
    """
    Get all the frequencies of all the sub-channels in each spw.
    TODO: put all the msmd in one fuction so that the object is created only once.
    """
    info("""Opening file to read the fieldnames: {0}""".format(conf.input.inputMS))
    msmd = msmetadata()
    msmd.open(msfile=conf.input.inputMS, maxcache=10000)
    return msmd.fieldnames()

def get_unflagged_channelIndexBoolList(conf):
    '''
    '''
    allFreqsList = get_all_freqsList(conf)
    # A list of indexes for all cube channels that will hold data.
    # Expl: ( 901e6 [Hz] - 890e6 [Hz] ) // 2.5e6 [Hz] = 4 [listIndex]
    channelIndexList = [
        int((freq - conf.input.startFreq) // conf.input.outputChanBandwidth) for freq in allFreqsList
    ]
    # remove negative values
    channelIndexList = np.array(channelIndexList)
    channelIndexList = channelIndexList[channelIndexList >= 0]
    maxChannelIndex = max(channelIndexList)
    # True if cube channel holds data, otherwise False
    channelIndexBoolList = []
    for ii in range(0, maxChannelIndex + 1):
        if ii in channelIndexList:
            channelIndexBoolList.append(True)
        else:
            channelIndexBoolList.append(False)
    return channelIndexBoolList

def get_unflagged_channelList(conf):
    channelList = []
    channelIndexBoolList = get_unflagged_channelIndexBoolList(conf)
    for i, channelBool in enumerate(channelIndexBoolList):
        if channelBool:
            channelList.append(i+1)
    return channelList


# HELPER
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def write_user_config_input(args):
    '''
    '''
    info("""Writing user input to file: {0}, {1}""".format(args, FILEPATH_CONFIG_USER))
    configString = "# TODO short discription.\n"
    configString += "# - - - - - - - - - - - - - - - - -\n\n"
    configString += "[input]\n"
    configInputStringArray = []
    with open(FILEPATH_CONFIG_USER, 'w') as f:
        for key, value in args.items():
            configInputStringArray.append(key + " = " + value)
        configString += "\n".join(configInputStringArray)
        f.write(configString)

def append_user_config_data(data):
    '''
    '''
    info("""Appending msdata to file: {0}, {1}""".format(data, FILEPATH_CONFIG_USER))
    configString = "\n\n[data]\n"
    configInputStringArray = []
    with open(FILEPATH_CONFIG_USER, 'a') as f:
        for key, value in data.items():
            configInputStringArray.append(key + " = " + str(value))
        configString += "\n".join(configInputStringArray)
        f.write(configString)


def create_directories(conf):
    """
    """
    for directory in list(conf.env.dirList):
        if not os.path.exists(directory):
            os.makedirs(directory)


def write_all_sbatch_files(conf):
    '''
    TODO: make this shorter and better
    '''
    # split and tclean
    basename = "cube_split_and_tclean"
    filename = basename + ".sbatch"
    info("Writing sbtach file: {0}".format(filename))
    sbatchDict = {
            'array': "1-" + str(len(conf.data.predictedOutputChannels)) + "%30",
            'job-name': basename,
            'output': "/logs/" + basename + "-%A-%a.out",
            'error': "/logs/" + basename + "-%A-%a.err",
            }
    command = '/usr/bin/singularity exec /data/exp_soft/containers/casa-6.simg python ' + basename + '.py --slurmArrayTaskId ${SLURM_ARRAY_TASK_ID}'
    write_sbtach_file(filename, command, sbatchDict)

    # buildcube
    basename = "cube_buildcube"
    filename = basename + ".sbatch"
    info("Writing sbtach file: {0}".format(filename))
    sbatchDict = {
            'array': "1-1%1",
            'job-name': basename,
            'output': "/logs/" + basename + "-%A-%a.out",
            'error': "/logs/" + basename + "-%A-%a.err",
            'cpus-per-task': 16,
            'mem': "200GB",
            }
    command = '/usr/bin/singularity exec /data/exp_soft/containers/python-3.6.img python3 ' + basename + '.py'
    write_sbtach_file(filename, command, sbatchDict)


@main_timer
@click.command(context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True,
))
#@click.argument('--inputMS', required=False)
@click.pass_context
def main(ctx):
    '''
    TODO: I made click super generic which is nice for development but we may
    want to change this for production.
    '''
    # get the click args in dot dotation
    args = DotMap(get_dict_from_click_args(ctx.args))
    info("Scripts arguments: {0}".format(args))

    # data: values derived from the measurement set like valid channels
    data = {}
    write_user_config_input(args)
    conf = get_config_in_dot_notation(templateFilename=FILEPATH_CONFIG_TEMPLATE, configFilename=FILEPATH_CONFIG_USER)

    data['predictedOutputChannels'] = get_unflagged_channelList(conf)
    data['fieldnames'] = get_fieldnames(conf)
    append_user_config_data(data)
    # reload conf after data got appended to user conf
    conf = get_config_in_dot_notation(templateFilename=FILEPATH_CONFIG_TEMPLATE, configFilename=FILEPATH_CONFIG_USER)

    create_directories(conf)

    write_all_sbatch_files(conf)


if __name__ == '__main__':
    main()
