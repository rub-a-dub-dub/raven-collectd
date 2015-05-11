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

def close_plugin:
    '''This will clean up all opened connections'''
    if ser is not None:
        ser.close()
        collectd.info("Serial port closed.")
    else:
        collectd.debug("Asking to close serial port, but it was never open.")

def initialise_plugin:
    '''This function opens the serial port looking for a RAVEn. Returns True if successful, False otherwise.'''
    try:
        ser = serial.Serial(serDevice, 115200, serial.EIGHTBITS, serial.PARITY_NONE, timeout=0.5)
        ser.close()
        ser.open()
        ser.flushInput()
        ser.flushOutput()
        collectd.info("Connected to: " + ser.portstr)
        return True
    except Exception as e:
        collectd.error("Cannot open serial port: " + str(e))
        return False

def isReady:
    '''This function is used to check if this object has been initialised correctly and is ready to process data'''
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
    val = collectd.Values(plugin='ravencollectd')
    val.type  = 'gauge'
    val.type_instance = 'instantdemand'
    val.plugin_instance = 'raven'
    val.values = [dataPt]
    val.dispatch()

def read_data:
    '''This function will read from the serial device, process the data and publish MQTT messages'''
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
                    collectd.debug("Start XML Tag found: " + rawline)
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
                            collectd.warning("Unrecognised (not implemented) XML Fragment")
                            collectd.warning(rawxml)
                    except Exception as e:
                      collectd.error("Exception triggered: " + str(e))
                    # reset rawxml
                    rawxml = ""
                    return
                # if it starts with a space, it's inside the fragment
                else:
                    rawxml = rawxml + rawline
                    collectd.debug("Normal inner XML Fragment: " + rawline)
            else:
                pass
    else:
        collectd.error("Was asked to begin reading/writing data without opening connections.")


collectd.register_init(initialise_plugin)
collectd.register_read(read_data)
collectd.register_shutdown(close_plugin)
