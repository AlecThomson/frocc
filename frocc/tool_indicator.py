#!python3
# -*- coding: utf-8 -*-

from logging import error, info

from frocc.config import FILEPATH_CONFIG_TEMPLATE, FILEPATH_CONFIG_USER
from frocc.lhelpers import (SEPERATOR, format_legend,
                            get_config_in_dot_notation, get_dict_from_tabFile,
                            get_std_via_mad, main_timer,
                            run_command_with_logging, update_CRPIX3)


def message():
    info("This is an indicator message. It helps to track execution times for those scripts that can not utilize the python logger itself. One of these scripts is the HDF5 converter, which gets executed in an sbatch file directly. This also means that the corrosponding log messages appear somewhere else, probably in the *.out file")

@main_timer
def main():
    #conf = get_config_in_dot_notation(templateFilename=FILEPATH_CONFIG_TEMPLATE, configFilename=FILEPATH_CONFIG_USER)

if __name__ == "__main__":
    main()
