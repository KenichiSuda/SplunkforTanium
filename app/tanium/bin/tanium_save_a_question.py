#!/usr/bin/python
###############################################################################
#
#
###############################################################################

import os
import re
import sys
import ssl
import socket
import httplib
import argparse
import HTMLParser
from datetime import datetime
import xml.etree.ElementTree as ET
import splunk.entity as entity
import splunk.clilib.cli_common as spcli
import importlib
import time

class TaniumQuestion:
    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        self.last_id = ""
        self.verbage = ""
        self.path = os.path.dirname(os.path.realpath(__file__))
        self.path = self.path.replace('\\', '/')
        
        with open(self.path + '/xml/getresult_template.xml') as x:
            self.GETRESULT_TEMPLATE = x.read()
            
        with open(self.path + '/xml/submit_nlp_template.xml') as x:
            self.SUBMIT_NLP_TEMPLATE = x.read()
            
        with open(self.path + '/xml/submit_raw_template.xml') as x:
            self.SUBMIT_RAW_TEMPLATE = x.read()
            
        with open(self.path + '/xml/save_question_template.xml') as x:
            self.SAVE_QUESTION_TEMPLATE = x.read()
            
        with open(self.path + '/xml/getsaved_template.xml') as x:
            self.GETSAVED_TEMPLATE = x.read()
            
        with open(self.path + '/xml/submit_template.xml') as x:
            self.SUBMIT_TEMPLATE = x.read()

    def check_xml_error(self, xml_text):
        """
        NOTE: Do not use this error check on the final results xml.
        The keyword 'ERROR' may be a valid sensor response!
        TODO: Fix the problem in the NOTE!
        """

        if re.search('ERROR', xml_text) != None:
            sys.stderr.write("THERE WAS AN ERROR PROCESSING THE XML REQUEST")
            sys.stderr.write(xml_text)
            print "ERROR,ERROR,ERROR"
            print "There was an error processing the xml request," + \
                  "Please run the script on the command line and check" + \
                  str(xml_text).replace(',', '_')
            sys.exit(0)


    def make_soap_connection(self, soap_message):
        try:
            webservice = httplib.HTTPSConnection(self.host,context=ssl._create_unverified_context())
        except Exception, e:
            raise Exception, "There was an error marshalling httplib %s" %str(e)
        webservice.putrequest("POST", "/soap")
        webservice.putheader("Host", self.host)
        webservice.putheader("User-Agent", "Python post")
        webservice.putheader("Content-type", "text/xml; charset=\"UTF-8\"")
        webservice.putheader("Content-length", "%d" % len(soap_message))
        webservice.putheader("SOAPAction", "\"\"")
        webservice.endheaders()
        webservice.send(soap_message)

        res = webservice.getresponse()
        # print res.status, res.reason
        data = res.read()
        webservice.close()
        return data
    
    def send_request_to_tanium(self, question,savename):
        """
        This function is complex but it will ask Tanium to make a guess on a
        question, rebuild the filter language around the question guess 
        """

        best_regex    = '(\<selects\>)(.*?)(\<\/selects\>)'
        filters_regex = '(\<filters\>)(.*?)(\<\/filters\>)'
        filter_regex  = '(\<filter\>)(.*?)(\<\/filter\>)'
        value_regex   = '(\<value\>)(.*?)(\<\/value\>)'
        op_regex      = '(\<operator\>)(.*?)(\<\/operator\>)'
        hash_regex    = '(\<hash\>)(.*?)(\<\/hash\>)'
        sensor_regex  = '(\<sensor\>)(.*?)(\<\/sensor\>)'
        id_ext_regex  = '(\<result_object\>\<question\>\<id\>)(.*?)(\<\/id\>)'
        verbage_regex = '(\<question_text\>)(.*?)(\<\/question_text\>)'
        post_sav_reg  = '(result_object\>\<saved_question\>\<id\>)(.*?)(\<\/id>)'
        sensor_list   = ""
        sensor_string = ""
        sensor_template = """<select>
        <filter>
        <value>%s</value>
        <operator>%s</operator>
        </filter>
        %s
        </select>"""
        
        # -------- ask Tanium if saved question already exists -----------
        soap_message = self.GETSAVED_TEMPLATE % (self.username, self.password, \
                                                 "GetResultInfo", savename)
        
        submitted_xml = self.make_soap_connection(soap_message)
        
        saved = re.findall('(SavedQuestionNotFound)',submitted_xml,re.DOTALL)
        
        if 'SavedQuestionNotFound' not in saved:
            return ["N/A","Saved question may already exist. " + \
                    "Please check Tanium console"]
        
        # ------------- ask nlp for best guess ------
        soap_message = self.SUBMIT_NLP_TEMPLATE % (self.username, self.password, \
                                                   question)
        
        guess_xml = self.make_soap_connection(soap_message)
        self.check_xml_error(guess_xml)
        
        #extract all the nlp guessed verbage
        parse_list=[]
        for element in re.finditer(verbage_regex, guess_xml, re.DOTALL):
            element = str(element.group(2))
            element = str(HTMLParser.HTMLParser().unescape(element))
            parse_list.append(element)
            
        self.verbage = parse_list[1]
        
        #extract the filters from the best guess
        filters_xml = re.search(filters_regex, guess_xml, re.DOTALL)
        if filters_xml != None:
            filter_collection = re.findall(filter_regex,filters_xml.group(0),
                                           re.DOTALL)
        else:
            filter_collection = []
        
        #extract the sensors from the best guess
        best_guess_xml = re.search(best_regex, guess_xml, re.DOTALL)
        best_guess_xml = best_guess_xml.group(2) + best_guess_xml.group(3)
        
        #match the sensors to the filters and compose xml filter + sensor
        #assume at most one filter for one sensor...this is ugly as sin
        
        sensors = re.findall(sensor_regex, best_guess_xml, re.DOTALL)
        
        for sensor in sensors:
            sensor_hash = re.search(hash_regex,sensor[1],re.DOTALL).group(2)
            sensor_string = ""
            for single_filter in filter_collection:
                filter_hash = re.search(hash_regex,single_filter[1],re.DOTALL).group(2)
                filter_op = re.search(op_regex,single_filter[1],re.DOTALL).group(2)
                filter_val = re.search(value_regex,single_filter[1],re.DOTALL).group(2)
                sensor = sensor[0]+sensor[1]+sensor[2]
                if sensor_hash == filter_hash:
                    sensor_string = sensor_template % (filter_val,filter_op,sensor)
                    #break?
                    
            if sensor_string == "":
                sensor_string = sensor_template % ("","",sensor)
            sensor_list = sensor_list + sensor_string
            
        best_guess_xml = "<question><selects>" + sensor_list + "</selects></question>"
        
        # -------------- submit best guess, get id --------
        soap_message = self.SUBMIT_RAW_TEMPLATE % (self.username, self.password, \
                                                   best_guess_xml)
        
        id_xml = self.make_soap_connection(soap_message)
        self.check_xml_error(id_xml)
        
        id_num = re.search(id_ext_regex, id_xml)
        id_num = id_num.group(2)
        self.last_id = id_num
        
        #-------- request last submit to be saved as a question -------------
        soap_message = self.SAVE_QUESTION_TEMPLATE % (self.username,
                                                       self.password,
                                                       savename,
                                                       self.verbage,
                                                       self.username,
                                                       self.last_id)
        
        post_save_xml = self.make_soap_connection(soap_message)
        saved_id_num = re.search(post_sav_reg, post_save_xml).group(2)
        return [self.verbage,saved_id_num]
        
    def ask_tanium_a_question(self, question, savename):
        self.last_state = self.send_request_to_tanium(question,savename)
        return self.last_state

def getCredentials(sessionKey):
    myapp = 'tanium'

    # need to deal with potentially multiple credentials
    # due to TA builder voodoo
    conf_dict = spcli.getConfStanzas('tanium_credential')

    # case where dictionary likely contains
    # disabled key - more ta factory voodoo
    if len(conf_dict) > 2:
        for i in conf_dict:
            try:
    # note have to use string literal comparisons...because reasons
                if conf_dict[i]['removed'] == '0' or (conf_dict[i].get("password") and conf_dict[i] != "default" ):
                    enabledUser = str(i)

            except:
                continue

    else:
        for i in conf_dict:
            try:
                if conf_dict[i] != "default":
                    enabledUser = str(i)
                    break
                else:
                    enabledUser = str(i)
                    break
            except Exception, e:
                raise Exception, "Error with credential map - check your setup: %s" % str(e)

    try:
        enabledUser
    except Exception, e:
        print """User: %s No Valid Tanium Credentials Found Check Your Setup. Error Output: %s""" %(conf_dict,str(e))
        raise Exception, "No valid users were found - check your setup: %s" % str(e)

    try:
        # list all credentials
        entities = entity.getEntities(['admin', 'passwords'], namespace=myapp,
                                      owner='nobody', sessionKey=sessionKey)
    except Exception, e:
        raise Exception, "Could not get %s credentials from splunk. Error: %s" % (myapp, str(e))

        # iterate through creds
        # and find which set is 'enabled' based on setup screen and
        # tanium_credential.conf
    for i, c in entities.items():
        if c['username'] == enabledUser:
            username = c['username']
            password = c['clear_password']
            break
        else:
            continue
    # return c['username'], c['clear_password']
    # TAB causes a funky separator
    try:
        password = password.split("splunk_cred_sep``", 1)[1]
    except Exception, e:
        print "Error attempting to decode the Tanium password - check your app setup"
        raise Exception, "Error attempting to decode password - check your app setup: %s" %str(e)

    return username, password


def get_input_config():

    sessionXml = sys.stdin.readline()

    if len(sessionXml) == 0:
       sys.stderr.write("Did not receive a session key from splunkd. " +
                        "Please enable passAuth in inputs.conf for this " +
                        "script\n")
       exit(2)

    #parse the xml sessionKey

    start = sessionXml.find('<authToken>') + 11
    stop = sessionXml.find('</authToken>')
    authTok = sessionXml[start:stop]


    username, password = getCredentials(authTok)
    return username, password



# ------------------------------MAIN MODULE--------------------------------------

def main():
    # sys.stderr = open('err.txt', 'w+')
    # Redirect error to out, so we can see any errors

    sessionXml = sys.stdin.readline()

    if len(sessionXml) == 0:
       sys.stderr.write("Did not receive a session key from splunkd. " +
                        "Please enable passAuth in inputs.conf for this " +
                        "script\n")
       exit(2)

    #parse the xml sessionKey

    start = sessionXml.find('<authToken>') + 11
    stop = sessionXml.find('</authToken>')
    authTok = sessionXml[start:stop]


    # now get tanium credentials - might exit if no creds are available
    username, passwd = getCredentials(authTok)
    sys.stderr = sys.stdout
    configuration_dict = spcli.getConfStanza('tanium_customized', 'taniumhost')
    tanium_server = configuration_dict['content']

    #parse the cli
    parser = argparse.ArgumentParser(description='Tanium Splunk Save A Question')
    
    """
    parser.add_argument(
        '--tanium',
        metavar = 'TANIUM',
        required = True,
        help = 'Tanium server')

    parser.add_argument(
        '--user',
        metavar = 'USER',
        required = True,
        help = 'user name')

    parser.add_argument(
        '--password',
        metavar = 'PASSWORD',
        required = True,
        help = 'user password')
    """
    
    parser.add_argument(
            '--question',
            metavar='QUESTION',
            required=True,
            help='nlp question')

    parser.add_argument(
            '--save_name',
            metavar='SAVENAME',
            required=True,
            help='The name to save the question under')

    args = vars(parser.parse_args())
    
    tanium   = tanium_server
    user     = username
    password = passwd

    #tanium    = args['tanium']
    #user      = args['user']
    #password  = args['password']
    question  = args['question']
    save_name = args['save_name']

    # end processing args now inst the Tanium class
    my_tanium = TaniumQuestion(tanium, user, password)

    # send the question to Tanium
    saved_resp = my_tanium.ask_tanium_a_question(question,save_name)
    print "Question,NLP Saved as,Saved Name,Tanium ID number"
    print question + "," + saved_resp[0] + "," + save_name + "," + saved_resp[1]
    

# ----------------------------MAIN ENTRY POINT-----------------------------------

if __name__ == '__main__':
    main()
