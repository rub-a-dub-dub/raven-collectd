# ravencollectd - ravencollectd.py
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; only version 2 of the License is applicable.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
#
# 
# Authors:
#   rub-a-dub-dub @ github
#
# About this plugin:
#   This is a plugin for collectd using its Python interface to read data from
#   a Rainforest Automation USB dongle (the RAVEn RFA-Z106).
# 
# collectd:
#   http://collectd.org
# collectd-python:
#   http://collectd.org/documentation/manpages/collectd-python.5.shtml
# Rainforest Automation RAVEn RFA-Z106:
#   http://rainforestautomation.com/rfa-z106-raven/
#

import sys
import time
import re
import xml.etree.ElementTree as ET
import serial
import collectd

serDevice = "/dev/ttyUSB0"
ser = None
reStartTag = re.compile('^<[a-zA-Z0-9]+>')
reEndTag = re.compile('^<\/[a-zA-Z0-9]+>')

def config_plugin(conf):
    '''This will configure the plugin with the serial device name'''
    global serDevice
    for node in conf.children:
        key = node.key.lower()
        val = node.values[0]

        if key == 'device':
            serDevice = val
        else:
            collectd.warning("ravencollectd: Unknown config key: %s." % key)
            continue

def close_plugin():
    '''This will clean up all opened connections'''
    global ser
    if ser is not None:
        ser.close()
        collectd.info("ravencollectd: Serial port closed.")
    else:
        collectd.debug("ravencollectd: Asking to close serial port, but it was never open.")

def initialise_plugin():
    '''This function opens the serial port looking for a RAVEn. Returns True if successful, False otherwise.'''
    global ser
    try:
        ser = serial.Serial(serDevice, 115200, serial.EIGHTBITS, serial.PARITY_NONE, timeout=0.5)
        ser.close()
        ser.open()
        ser.flushInput()
        ser.flushOutput()
        collectd.info("ravencollectd: Connected to: " + ser.portstr)
        return True
    except Exception as e:
        collectd.error("ravencollectd: Cannot open serial port: " + str(e))
        return False

def isReady():
    '''This function is used to check if this object has been initialised correctly and is ready to process data'''
    global ser
    return (ser is not None)

def getInstantDemandKWh(xmltree):
    '''Returns a single float value for the Demand from an Instantaneous Demand response from RAVEn'''
    # Get the Instantaneous Demand
    fDemand = float(int(xmltree.find('Demand').text,16))
    fResult = calculateRAVEnNumber(xmltree, fDemand)
    return fResult

def calculateRAVEnNumber(xmltree, value):
    '''Calculates a float value from RAVEn using Multiplier and Divisor in XML response'''
    # Get calculation parameters from XML - Multiplier, Divisor
    fDivisor = float(int(xmltree.find('Divisor').text,16))
    fMultiplier = float(int(xmltree.find('Multiplier').text,16))
    if (fMultiplier > 0 and fDivisor > 0):
        fResult = float( (value * fMultiplier) / fDivisor)
    elif (fMultiplier > 0):
        fResult = float(value * fMultiplier)
    else: # (Divisor > 0) or anything else
        fResult = float(value / fDivisor)
    return fResult*1000

def write_to_collectd(dataPt):
    '''This actually writes the data to collectd'''
    val = collectd.Values(plugin='ravencollectd',type='gauge')
    val.type_instance = 'instantdemand'
    val.plugin_instance = 'raven'
    val.dispatch(values=[dataPt])

def read_data():
    '''This function will read from the serial device, process the data and write to collectd'''
    global ser
    if isReady():
        # begin listening to RAVEn
        rawxml = ""

        while True:
            # wait for /n terminated line on serial port (up to timeout)
            rawline = ser.readline()
            # remove null bytes that creep in immediately after connecting
            rawline = rawline.strip('\0')
            # only bother if this isn't a blank line
            if len(rawline) > 0:
                # start tag
                if reStartTag.match(rawline):
                    rawxml = rawline
                    collectd.debug("ravencollectd: Start XML Tag found: " + rawline)
                # end tag
                elif reEndTag.match(rawline):
                    rawxml = rawxml + rawline
                    collectd.debug("End XML Tag Fragment found: " + rawline)
                    try:
                        xmltree = ET.fromstring(rawxml)
                        if xmltree.tag == 'InstantaneousDemand':
                            write_to_collectd(getInstantDemandKWh(xmltree))
                            # collectd.debug(getInstantDemandKWh(xmltree))
                        else:
                            collectd.info("ravencollectd: Unrecognised (not implemented) XML Fragment")
                            collectd.info(rawxml)
                    except Exception as e:
                      collectd.warning("ravencollectd: Exception triggered: " + str(e))
                    # reset rawxml
                    rawxml = ""
                    return
                # if it starts with a space, it's inside the fragment
                else:
                    rawxml = rawxml + rawline
                    collectd.debug("ravencollectd: Normal inner XML Fragment: " + rawline)
            else:
                pass
    else:
        collectd.warning("ravencollectd: Was asked to begin reading/writing data without opening connections.")


collectd.register_init(initialise_plugin)
collectd.register_config(config_plugin)
collectd.register_read(read_data)
collectd.register_shutdown(close_plugin)
